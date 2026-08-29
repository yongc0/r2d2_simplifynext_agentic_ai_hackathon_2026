"""The wire shapes, matching `web/src/api/types.ts` field for field.

These are deliberately NOT the internal pydantic models. `src/schemas/views.py`
is what the system builds internally; this is what crosses the network, in the
camelCase the client expects.

The translation happens in exactly one place — `src/api/mapping.py` — so the
drift the client's `wire.ts` documents has one counterpart here rather than
being re-decided per endpoint.

INVARIANT NOTE: none of the pre-reveal models below has a field for a name, a
photo, an age, a distance or a place. `RevealOut` is the only model in this file
that carries an identity, and only `POST /consent` can produce one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The client's vocabulary. Kept as literals rather than imported from
# `src.schemas.core` because the CLIENT state machine is deliberately a
# different set — see `web/src/api/wire.ts`, note 2.
ClientState = Literal[
    "IDLE",
    "WINDOW_OPEN",
    "NOTIFIED",
    "PENDING_ACCEPT",
    "CONNECTED",
    "CALL_ENDED",
    "PENDING_CONSENT",
    "REVEALED",
    "CLOSED",
    "ABANDONED",
]

#: Matches `src.schemas.core.Intent` exactly. The client's FRONTEND.md draft
#: spelled these `partner_long` / `partner_short`; the backend values won,
#: because they are the ones on the wire.
Intent = Literal["partner_long_term", "partner_short_term", "friends"]


class EncounterCardOut(BaseModel):
    """Today's encounter, as the client renders it.

    INVARIANT 2: no name, no photo, no age, no initial. `handle` is a
    pseudonym from a fixed word list, never derived from a name.

    INVARIANT 1: `overlapHint` is a rendered phrase produced from a coarse time
    bucket. There is no field here that could carry a place or a distance, and
    nothing upstream of it knows one.
    """

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(serialization_alias="encounterId")
    state: ClientState
    intent: Intent
    handle: str
    shared_interests: list[str] = Field(serialization_alias="sharedInterests")
    overlap_hint: str = Field(serialization_alias="overlapHint")
    window_closes_at: str = Field(serialization_alias="windowClosesAt")
    call_seconds: int = Field(serialization_alias="callSeconds")


class RespondIn(BaseModel):
    accept: bool


class CallTickOut(BaseModel):
    elapsed: int
    amplitude: float
    speaker: Literal["local", "remote", "silence"]


class ConversationPromptOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    at_second: int = Field(serialization_alias="atSecond")
    #: The stable id of the thing both people raised. Present so fidelity is
    #: checkable by comparison rather than by reading two sentences and
    #: agreeing they are about the same subject.
    topic: str
    text: str
    #: What each person actually said. Two entries, one per person, LOOKED UP
    #: from the transcript in `call_fixture.py` rather than written beside the
    #: prompt — a prompt whose commonality is not in the transcript cannot be
    #: constructed.
    grounded_in: list[str] = Field(serialization_alias="groundedIn")


class CallScriptOut(BaseModel):
    ticks: list[CallTickOut]
    prompts: list[ConversationPromptOut]


class ConsentIn(BaseModel):
    yes: bool


class RevealOut(BaseModel):
    """The only model in this file that carries an identity.

    Produced exclusively by `POST /consent` on a mutual yes, and built by
    `src.safety.consent.build_reveal`, which refuses without one.
    """

    model_config = ConfigDict(populate_by_name=True)

    person_id: str = Field(serialization_alias="personId")
    display_name: str = Field(serialization_alias="displayName")
    #: Seeds a generated illustration. Never a photograph, and there is no
    #: field here that could hold a URL to one (INVARIANT 7).
    avatar_seed: str = Field(serialization_alias="avatarSeed")
    shared_interests: list[str] = Field(serialization_alias="sharedInterests")


class ConsentOut(BaseModel):
    """The result of the post-call gate.

    INVARIANT 3 lives at this boundary as well as in the client. `outcome`
    distinguishes `declined` from `no_response` so the demo controls can film
    both branches — and the client must not branch on the difference. The
    close-out it renders takes no props at all, so it cannot.

    What is NOT here: any indication of who declined, when they answered, or
    whether they answered at all. `person` is null on every non-mutual ending,
    and the payload is otherwise byte-identical between them.
    """

    outcome: Literal["mutual", "declined", "no_response"]
    person: RevealOut | None = None


class LockInOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lock_in_id: str = Field(serialization_alias="lockInId")
    person: RevealOut
    opened_at: str = Field(serialization_alias="openedAt")
    last_contact_at: str | None = Field(serialization_alias="lastContactAt")
    state: Literal["active", "quiet", "released"]


class ContinuityBriefOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lock_in_id: str = Field(serialization_alias="lockInId")
    #: Must quote something the pair actually discussed. A brief with nothing to
    #: cite is a reminder, not continuity, and is not produced.
    line: str
    suggested_action: str = Field(serialization_alias="suggestedAction")
    source_encounter_id: str = Field(serialization_alias="sourceEncounterId")


class AgentEventOut(BaseModel):
    """One row in the Director panel."""

    model_config = ConfigDict(populate_by_name=True)

    ts: str
    agent: Literal[
        "onboarding", "match", "delivery", "continuity",
        "communication", "date", "guardian", "safety",
    ]
    action: str
    detail: str
    duration_ms: int = Field(serialization_alias="durationMs")
    tokens: int | None = None
    status: Literal["ok", "retry", "error"]


class HealthOut(BaseModel):
    """What the client and the pilot runbook check.

    Reports the provider so a run can never be mistaken for a model run when it
    is not one — the same discipline the metrics reports follow.
    """

    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    provider: str
    model_reasoning: str = Field(serialization_alias="modelReasoning")
    model_fast: str = Field(serialization_alias="modelFast")
    call_seconds: int = Field(serialization_alias="callSeconds")
    world_users: int = Field(serialization_alias="worldUsers")


# ---------------------------------------------------------------------------
# Onboarding (FRONTEND.md §5.1)
# ---------------------------------------------------------------------------


class ExtractIn(BaseModel):
    """One turn of intake.

    The CUMULATIVE transcript, not the latest message — `OnboardingAgent`
    extracts over everything the person has said, and a per-message call would
    keep asking about what they told us three turns ago.
    """

    transcript: str


class ExtractionOut(BaseModel):
    """What the Onboarding Agent understood, for the client's chip panel.

    INVARIANT 5 (no height, appearance or photo-based filtering): there is no
    field here for a physical attribute, and `_enforce_rules` strips those words
    before they could reach one. The client's `ChipKind` has no member for one
    either, so neither side can render it.

    `follow_up` is the agent's wording, deliberately. The neutral phrasing of
    the intent question is part of the rule that intent is never inferred
    (§13.1), so it lives with the agent that enforces the rule rather than in a
    screen that could quietly start leaning.
    """

    model_config = ConfigDict(populate_by_name=True)

    intents: list[Intent]
    interests: list[str]
    values: list[str]
    #: Coarse time buckets only. Never a clock time, never a place.
    availability: list[str]
    languages: list[str]
    unresolved: list[str]
    follow_up: str | None = Field(default=None, serialization_alias="followUp")


# ---------------------------------------------------------------------------
# Date planning (ARCHITECTURE §13.6)
# ---------------------------------------------------------------------------


class DateStopOut(BaseModel):
    """One place in a suggested evening.

    INVARIANT 3: no address, cell, coordinate or distance field, and there must
    not be one. A stop is a KIND of place — "a hawker centre, one dish each and
    swap" — never a named business at a location.
    """

    model_config = ConfigDict(populate_by_name=True)

    venue_id: str = Field(serialization_alias="venueId")
    activity: str
    category: Literal["activity", "food", "drink"]
    #: Required, not optional, so a partner venue cannot cross the wire without
    #: its label.
    is_commercial_partner: bool = Field(serialization_alias="isCommercialPartner")


class DatePathOut(BaseModel):
    """One suggested evening: a thing to do, and somewhere to eat or sit."""

    model_config = ConfigDict(populate_by_name=True)

    path_id: str = Field(serialization_alias="pathId")
    headline: str
    stops: list[DateStopOut]
    #: Interests BOTH people listed. Never empty — an ungrounded suggestion is
    #: a guess, and the agent does not build one.
    grounded_in: list[str] = Field(serialization_alias="groundedIn")
    rationale: str
    proposed_bucket: str = Field(serialization_alias="proposedBucket")


class DatePlanOut(BaseModel):
    """Up to three genuinely different evenings, or none with a reason why."""

    model_config = ConfigDict(populate_by_name=True)

    paths: list[DatePathOut]
    #: Says why a plan is short or empty, so it reads as a fact about the pair
    #: rather than as a failure.
    note: str = ""


# ---------------------------------------------------------------------------
# Guardian (ARCHITECTURE §13.7)
# ---------------------------------------------------------------------------


class GuardianCheckInIn(BaseModel):
    """The answer to Guardian's private check-in.

    Deliberately just a boolean. There is no free-text field, and adding one
    would be a decision rather than a convenience: a person who has used a
    safety feature has already told us the thing that matters, and asking them
    to write it out is asking them to relive it before they are ready. What
    happens next is an operator's job, not a form's.
    """

    all_right: bool = Field(alias="allRight")

    model_config = ConfigDict(populate_by_name=True)


class GuardianCheckInOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    recorded: bool
    #: What the person is told, in plain words. Never implies a human has
    #: already seen it — see the route.
    message: str
