"""What each agent must emit.

One model per agent output. These are the models the schema-validation metric
(organisers' metric 1, target >= 98%) is measured against: an output counts as
a pass only if it validates on the *first* attempt.

Constraints here are not decoration. `MatchDecision.confidence` is bounded
because an unbounded confidence is not a probability; `ConversationPrompt`
carries `grounded_in` because a prompt that cannot name what it was grounded in
is a hallucinated commonality, which CLAUDE.md calls out as both a graded
fidelity failure and a real user harm.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.core import Intent, TimeBucket, VerificationTier


class OnboardingExtraction(BaseModel):
    """Onboarding — *Extraction*. Conversational intake turned into structure.

    `intents` is deliberately allowed to be empty at this layer: §13.1 says
    intent is never inferred from tone, so an intake that did not name one must
    be able to say so rather than being forced to guess. The agent then asks.
    """

    model_config = ConfigDict(extra="forbid")

    intents: list[Intent] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list, max_length=20)
    values: list[str] = Field(default_factory=list, max_length=10)
    personality: str = ""
    lifestyle: str = ""
    languages: list[str] = Field(default_factory=list)
    availability_window: list[TimeBucket] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list, max_length=10)
    verification_tier: VerificationTier = VerificationTier.UNVERIFIED
    #: The fields the user explicitly permitted to be used for matching.
    matchable_fields: list[str] = Field(default_factory=list)
    #: What the extraction could not determine and must ask about. Empty means
    #: the intake is complete.
    unresolved: list[str] = Field(default_factory=list)

    @field_validator("interests", "values", "dealbreakers", "languages")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            cleaned = value.strip().lower()
            if cleaned and cleaned not in out:
                out.append(cleaned)
        return out


class MatchDecision(BaseModel):
    """Match — *Decision-Support*. §13.2.

    The claim this model makes, and the claim we defend: it estimates who is
    worth three minutes from stated preferences, interests, personality and
    behavioural feedback. It does not predict attraction. Joel, Eastwick &
    Finkel (2017) showed ML over 100+ self-reported traits cannot predict
    relationship-specific attraction above chance, so `confidence` is a
    confidence in *this selection being worth a call*, not a probability of
    anything romantic — and `eval/run_arms.py` benchmarks it against random
    assignment precisely so the claim can be falsified.
    """

    model_config = ConfigDict(extra="forbid")

    day: Date
    user_id: str
    candidate_id: str
    #: Why this person, in language that could be shown to the user. It must
    #: not name a place, a distance, or anything identifying — the guardrail in
    #: `src/safety/guardrails.py` checks it before it is ever rendered.
    rationale: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)
    #: Which shortlisted candidates were considered. Kept for the trace and for
    #: the fairness audit; never rendered.
    considered: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_self(self) -> MatchDecision:
        if self.user_id == self.candidate_id:
            raise ValueError("the Match Agent selected the user themselves")
        if self.considered and self.candidate_id not in self.considered:
            raise ValueError(
                f"selected candidate {self.candidate_id!r} was not on the "
                f"shortlist {self.considered} — the decision is not explainable"
            )
        return self


class ContinuityAction(BaseModel):
    """Continuity — *Personalized*. §13.4. The "over time" agent.

    `reference` is what separates this from a generic nudge: it must quote
    something the pair actually discussed. A re-entry with no reference is a
    notification, and the product already has enough of those.
    """

    model_config = ConfigDict(extra="forbid")

    lockin_id: str
    user_id: str
    action: Literal["brief", "re_entry", "propose_meeting", "adjust_pace", "release"]
    message: str = Field(min_length=1, max_length=400)
    #: The prior-call note this action is grounded in. Required for `re_entry`
    #: and `propose_meeting`; that is what makes week 5 differ from week 1.
    reference: str = ""
    #: For `adjust_pace`, the new preferred gap in days.
    pace_pref_days: float | None = Field(default=None, ge=0.5, le=30.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _grounded(self) -> ContinuityAction:
        if self.action in ("re_entry", "propose_meeting") and not self.reference.strip():
            raise ValueError(
                f"a {self.action!r} action must cite what the pair actually "
                "discussed; an ungrounded re-entry is a generic nudge (§13.4)"
            )
        if self.action == "adjust_pace" and self.pace_pref_days is None:
            raise ValueError("an adjust_pace action must carry pace_pref_days")
        return self


class ConversationPrompt(BaseModel):
    """Communication — *Creative/Generative*. §13.5, opt-in.

    `grounded_in` holds the two things each person actually said. A prompt that
    cannot fill both sides is a hallucinated commonality: CLAUDE.md forbids it
    and metric 6 measures it.
    """

    model_config = ConfigDict(extra="forbid")

    lockin_id: str
    prompt: str = Field(min_length=1, max_length=280)
    #: [something A said, something B said]. Exactly two entries.
    grounded_in: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _both_sides_real(self) -> ConversationPrompt:
        if any(not g.strip() for g in self.grounded_in):
            raise ValueError(
                "grounded_in must quote something each person actually said; "
                "an empty side means the shared interest was invented (§13.5)"
            )
        return self


class DateSuggestion(BaseModel):
    """Date — *Decision-Support / Transaction*. §13.6.

    `is_commercial_partner` is mandatory rather than optional so a partner
    venue cannot be rendered without its label.
    """

    model_config = ConfigDict(extra="forbid")

    lockin_id: str
    venue_id: str
    activity: str = Field(min_length=1, max_length=120)
    #: Why this suits *these two*, from their shared interests.
    rationale: str = Field(min_length=1, max_length=300)
    fit_score: float = Field(ge=0.0, le=1.0)
    is_commercial_partner: bool
    proposed_bucket: TimeBucket


class DateStop(BaseModel):
    """One place in a date path.

    INVARIANT 3: there is no address, cell, coordinate or distance field here,
    and there must not be one. A stop is a KIND of place — "a hawker centre,
    one dish each and swap" — not a named business at a location. That keeps
    the plan actionable without it ever becoming a map.
    """

    model_config = ConfigDict(extra="forbid")

    venue_id: str
    activity: str = Field(min_length=1, max_length=120)
    category: Literal["activity", "food", "drink"]
    #: Mandatory, for the same reason as on `DateSuggestion`: a partner venue
    #: cannot be constructed without its label.
    is_commercial_partner: bool


class DatePath(BaseModel):
    """One suggested evening — a thing to do, and somewhere to eat or sit.

    A path rather than a single venue because "we should meet sometime" is
    where most of these connections die, and one venue is only slightly harder
    to say no to than nothing. A short itinerary is a plan a person can accept.

    `grounded_in` lists interests BOTH people actually stated. The Date Agent
    reads it out of the intersection of the two profiles, so a path cannot
    claim a commonality neither of them has — the same rule the Communication
    Agent follows for call prompts, and for the same reason.
    """

    model_config = ConfigDict(extra="forbid")

    path_id: str
    lockin_id: str
    #: Composed from the stops, never written by hand or by a model.
    headline: str = Field(min_length=1, max_length=200)
    stops: list[DateStop] = Field(min_length=1, max_length=3)
    #: Interests both of them listed. Empty is not allowed: an ungrounded path
    #: is a guess dressed as a suggestion.
    grounded_in: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=300)
    fit_score: float = Field(ge=0.0, le=1.0)
    proposed_bucket: TimeBucket

    @property
    def has_commercial_partner(self) -> bool:
        return any(stop.is_commercial_partner for stop in self.stops)


class DatePlan(BaseModel):
    """What the Date Agent returns: a small set of genuinely different options.

    Three, because one is a demand and a list is a chore. They are required to
    differ in their lead activity — see `DateAgent.plan` — so the person is
    choosing between evenings rather than between synonyms.
    """

    model_config = ConfigDict(extra="forbid")

    lockin_id: str
    paths: list[DatePath] = Field(max_length=3)
    #: Stated when the agent could not fill all three, so a short list reads as
    #: a fact about the pair rather than as a bug.
    note: str = ""


class GuardianPlan(BaseModel):
    """Guardian — *Embedded*. §13.7.

    Never imitates a system or OS-level alert. `channel` is restricted to the
    two honest options; there is no "fake system notification" to choose.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    channel: Literal["in_app_call", "in_app_message"]
    excuse_text: str = Field(min_length=1, max_length=200)
    check_in_after_minutes: int = Field(ge=1, le=240)
    trusted_contact_notified: bool = False


class SafetyVerdict(BaseModel):
    """Trust & Safety — *Embedded*, cross-cutting. §13.8.

    Deterministic. No model decides this (INVARIANT 6). `categories` names what
    fired so a failure is actionable rather than "blocked".
    """

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    categories: list[str] = Field(default_factory=list)
    #: What the user is told. Empty when allowed.
    user_message: str = ""
    #: What the operator sees. Never shown to a user.
    detail: str = ""

    @model_validator(mode="after")
    def _blocked_says_why(self) -> SafetyVerdict:
        if not self.allowed and not self.categories:
            raise ValueError(
                "a blocked verdict must name at least one category — "
                "'blocked' with no reason is not actionable"
            )
        return self


# ---------------------------------------------------------------------------
# What the MODEL is asked for, as opposed to what the system stores
# ---------------------------------------------------------------------------
#
# A model should be asked for a judgement, never for bookkeeping. `day`,
# `user_id` and `lockin_id` are facts the caller already holds; asking the
# model to reproduce them gives it three more chances to fail validation and
# turns the schema-validation metric into a measure of our prompt rather than
# of the model's output. So the model fills in a narrow "draft", and the agent
# composes the full record around it.
#
# Every draft below is a strict subset of the model it feeds, so the validation
# rules that matter — a bounded confidence, a grounded re-entry, two citations
# — still apply at the point the model's answer arrives.


class MatchChoice(BaseModel):
    """What the Match Agent asks a model for. §13.2."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)


class ContinuityDraft(BaseModel):
    """What the Continuity Agent asks a model for. §13.4.

    The *choice* of action belongs to the rules in `_what_is_needed`; this is
    the model's wording for it, and its judgement of how confident to be.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["brief", "re_entry", "propose_meeting", "adjust_pace", "release"]
    message: str = Field(min_length=1, max_length=400)
    reference: str = ""
    pace_pref_days: float | None = Field(default=None, ge=0.5, le=30.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ConversationDraft(BaseModel):
    """What the Communication Agent asks a model for. §13.5.

    `grounded_in` keeps its two-entry rule here, at the boundary, so an
    ungrounded prompt fails on arrival rather than later.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=280)
    grounded_in: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _both_sides_real(self) -> ConversationDraft:
        if any(not g.strip() for g in self.grounded_in):
            raise ValueError(
                "grounded_in must quote something each person actually said"
            )
        return self
