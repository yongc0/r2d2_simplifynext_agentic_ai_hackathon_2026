"""Date Studio — the shapes that cross a boundary.

Spark finds one person a day. Date Studio is what it does once you have found
them: fixed constraints in, three grounded plans out, structured feedback back,
and a memory the person can read and correct.

TWO CLAIMS THIS MODULE IS BUILT TO KEEP HONEST

*It remembers.* Preferences and feedback are durable rows, not a field on a
session object, and `DateMemoryItem` carries where each one came from — chosen
explicitly, or inferred from what someone did — so the interface can show the
difference and the person can correct it.

*It does not learn a model.* Improvement is deterministic re-ranking over those
rows. Nothing here trains anything, and no docstring or copy anywhere may imply
otherwise.

WHAT THESE MODELS DELIBERATELY CANNOT CARRY

There is no address, coordinate, cell, distance or map field on anything below,
and there must not be one. A date plan is the only thing in Spark permitted to
point somewhere, and it is safe only because the ranking that produces it cannot
read a location — see `ARCHITECTURE.md` §13.6.

`owner_id` appears on stored records but is NEVER accepted from a client. The
API derives it from the session, because a client that can name the owner of a
memory item can read and rewrite somebody else's.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# The dimensions
# ---------------------------------------------------------------------------
#
# Fixed vocabularies rather than free text, on purpose. A planning form built
# from an open chat box has to interpret what somebody typed, and interpretation
# is exactly where a recommender starts inventing. These are also the units the
# memory is stored in, so what Spark remembers can be shown back word for word.

Mood = Literal["easy", "playful", "adventurous", "meaningful"]
Budget = Literal["free", "under_20", "under_50", "flexible"]
Duration = Literal["one_hour", "two_hours", "whole_evening"]
Energy = Literal["low", "medium", "high"]
Format = Literal["food", "activity", "outdoors", "learning", "event"]

#: Which dimension a memory item is about. Kept in step with the fields on
#: `DatePlanningPreferences`; `tests/test_date_studio.py` asserts they match.
MemoryDimension = Literal["mood", "budget", "duration", "energy", "format"]

#: How Spark came to believe it. `explicit` is the person choosing and asking to
#: be remembered; `feedback` is inferred from what they did with a plan. The
#: distinction is shown in the interface and is load-bearing in the scorer.
MemorySource = Literal["explicit", "feedback"]

PlanShape = Literal["easy", "new", "light"]

FeedbackAction = Literal["saved", "rejected", "completed"]

#: Why a plan was not right. Chips, not a text box: a rejection reason has to be
#: something the scorer can act on, and "meh" is not.
RejectionReason = Literal[
    "too_expensive",
    "too_long",
    "too_active",
    "too_quiet",
    "too_crowded",
    "wrong_time",
    "already_done",
    "not_our_style",
]

#: Confidence for something the person chose themselves. Nothing inferred may
#: reach it — see `MAX_INFERRED_CONFIDENCE`.
EXPLICIT_CONFIDENCE = 1.0

#: The ceiling on anything learned from behaviour.
#:
#: A single rejection is not a permanent dislike. Somebody who says "too
#: expensive" once on a Tuesday has not told us they are frugal, and a
#: recommender that treats it that way stops offering things they would have
#: liked — while looking, from the inside, like it is learning.
MAX_INFERRED_CONFIDENCE = 0.6

#: How far one piece of feedback may move a belief.
CONFIDENCE_STEP = 0.2


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class DatePlanningPreferences(BaseModel):
    """What the pair want *this time*.

    Every field is optional: the form must be usable without answering
    everything, and an unset dimension means "no opinion", not a default the
    scorer should invent.
    """

    model_config = ConfigDict(extra="forbid")

    mood: Mood | None = None
    budget: Budget | None = None
    duration: Duration | None = None
    energy: Energy | None = None
    #: More than one is allowed — "food or outdoors" is a real answer.
    formats: list[Format] = Field(default_factory=list, max_length=5)
    #: Must be one of the pair's genuinely shared buckets. The API checks it
    #: against `spark-calendar` rather than trusting the client.
    time_bucket: str | None = None

    def as_pairs(self) -> list[tuple[str, str]]:
        """(dimension, value) for everything actually set.

        One place that flattens preferences, so the scorer and the memory
        writer cannot disagree about what a preference *is*.
        """
        pairs: list[tuple[str, str]] = []
        for dimension in ("mood", "budget", "duration", "energy"):
            value = getattr(self, dimension)
            if value is not None:
                pairs.append((dimension, value))
        for fmt in self.formats:
            pairs.append(("format", fmt))
        return pairs


class DatePlanRequest(BaseModel):
    """One press of Generate."""

    model_config = ConfigDict(extra="forbid")

    preferences: DatePlanningPreferences = Field(
        default_factory=DatePlanningPreferences
    )
    #: OPT-IN, and it defaults to off.
    #:
    #: "I am tired tonight" is context, not a preference, and a system that
    #: quietly promotes tonight's mood into a durable belief will be wrong about
    #: someone forever without ever having been told anything untrue. The person
    #: has to ask to be remembered.
    remember: bool = False


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class DateMemoryItem(BaseModel):
    """One thing Spark remembers, and where it got it.

    Two scopes:

      `user`   — true of this person across every connection ("usually picks
                 something under $20").
      `lockin` — true only of one pair ("they rejected crowded evenings").

    A lock-in item must never influence a different lock-in. Someone's feedback
    about one person is not a fact about them in general, and treating it as one
    would leak the shape of a private reaction into an unrelated plan.
    """

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    #: Set by the server from the session, never from a request body.
    owner_id: str
    scope: Literal["user", "lockin"]
    #: Required when `scope` is "lockin", forbidden otherwise — enforced below.
    lockin_id: str | None = None
    dimension: MemoryDimension
    value: str = Field(min_length=1, max_length=64)
    source: MemorySource
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    #: Soft delete, so removing a preference is recoverable and the audit trail
    #: stays readable. Nothing reads an inactive row when scoring.
    active: bool = True

    @model_validator(mode="after")
    def _scope_and_lockin_agree(self) -> DateMemoryItem:
        if self.scope == "lockin" and not self.lockin_id:
            raise ValueError(
                "a lock-in scoped memory item needs a lockin_id; without one it "
                "would silently behave as a user-wide preference"
            )
        if self.scope == "user" and self.lockin_id:
            raise ValueError(
                "a user scoped memory item must not carry a lockin_id — that is "
                "how one connection's feedback leaks into another"
            )
        return self

    @model_validator(mode="after")
    def _inferred_confidence_is_capped(self) -> DateMemoryItem:
        if self.source == "feedback" and self.confidence > MAX_INFERRED_CONFIDENCE:
            raise ValueError(
                f"inferred confidence {self.confidence} exceeds the cap "
                f"{MAX_INFERRED_CONFIDENCE}: something learned from behaviour "
                "must never outrank something the person chose"
            )
        return self


# ---------------------------------------------------------------------------
# Plans and feedback
# ---------------------------------------------------------------------------


class DatePlanRecord(BaseModel):
    """A snapshot of a plan that was actually shown.

    Stored so later feedback can be validated against something real: without
    it, a client could submit feedback for a plan that was never offered, and
    the memory would fill with beliefs derived from nothing.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    lockin_id: str
    owner_id: str
    shape: PlanShape
    #: The lead venue, for the repetition penalty.
    lead_venue_id: str
    #: Bands as shown, so feedback like "too expensive" has something to attach
    #: to without re-deriving it from a catalogue that may have changed.
    budget_band: Budget
    duration_band: Duration
    energy_band: Energy
    formats: list[Format] = Field(default_factory=list, max_length=5)
    created_at: datetime


class DatePlanFeedback(BaseModel):
    """What someone did with a plan.

    About the RECOMMENDATION, never about the relationship. Spark does not ask
    whether a date went well or whether somebody liked you: that is not ours to
    grade, and a product that scores it teaches people to perform.
    """

    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    plan_id: str
    lockin_id: str
    owner_id: str
    action: FeedbackAction
    #: Only meaningful with `rejected`.
    reasons: list[RejectionReason] = Field(default_factory=list, max_length=8)
    created_at: datetime
    #: Feedback can be changed. The newest active row decides the score; the
    #: superseded ones stay readable, which is what makes the memory auditable
    #: rather than merely current.
    active: bool = True

    @model_validator(mode="after")
    def _reasons_belong_to_a_rejection(self) -> DatePlanFeedback:
        if self.reasons and self.action != "rejected":
            raise ValueError(
                f"rejection reasons were given with action {self.action!r}; "
                "a reason explains a no and means nothing beside a yes"
            )
        return self


#: Which memory dimension a rejection reason argues about, and in which
#: direction. Read by the scorer, and the ONLY place a reason becomes a belief.
#:
#: Note what is absent: `not_our_style` and `already_done` map to nothing. They
#: are real things to tell us and they are recorded, but neither says which
#: dimension was wrong, and guessing would be inventing a preference from a
#: shrug. `already_done` is handled by the repetition penalty instead.
REASON_TO_DIMENSION: dict[str, tuple[str, str]] = {
    "too_expensive": ("budget", "cheaper"),
    "too_long": ("duration", "shorter"),
    "too_active": ("energy", "lower"),
    "too_quiet": ("energy", "higher"),
    "too_crowded": ("format", "avoid_event"),
    "wrong_time": ("time", "other"),
}
