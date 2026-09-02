"""The durable domain model — docs/ARCHITECTURE.md §15.

Two things in here carry the product's guarantees and are worth reading twice:

  `EncounterState`  the state machine of §14, with the legal transitions
                    declared as data. A transition that is not in TRANSITIONS
                    cannot happen — `Encounter.transition_to` refuses it.
  `PrivateIdentity` the fields that must never reach another user before mutual
                    consent. Held apart from `Profile` so that "did we leak an
                    identity" is a question about one small class, not a review
                    of every string in the system.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Intent(StrEnum):
    """What someone says they are here for.

    Onboarding rule (§13.1): intent is NEVER inferred from tone. If the user did
    not name it, it is not set. `test_intent.py` holds that rule to account.
    """

    PARTNER_LONG_TERM = "partner_long_term"
    PARTNER_SHORT_TERM = "partner_short_term"
    FRIENDS = "friends"


class VerificationTier(StrEnum):
    """How strongly the account is verified. Higher tiers may require a match to
    also be verified; the rule is in `src/agents/match.py`, not here."""

    UNVERIFIED = "unverified"
    PHONE = "phone"
    GOVERNMENT_ID = "government_id"      # simulated Singpass-tier, never real


class TimeBucket(StrEnum):
    """Coarse time-of-day for an overlap. Never a timestamp — a timestamp plus a
    cell is close to a location fix."""

    EARLY_MORNING = "early_morning"      # 05:00-08:00
    MORNING = "morning"                  # 08:00-11:00
    MIDDAY = "midday"                    # 11:00-14:00
    AFTERNOON = "afternoon"              # 14:00-17:00
    EVENING = "evening"                  # 17:00-21:00
    NIGHT = "night"                      # 21:00-05:00


class EncounterState(StrEnum):
    """§14. `ABANDONED` and `CLOSED` are normal terminal states, not errors, and
    must produce no observable signal to the other party."""

    PROFILED = "PROFILED"
    POOLED = "POOLED"
    SELECTED = "SELECTED"
    NOTIFIED = "NOTIFIED"
    PENDING_ACCEPT = "PENDING_ACCEPT"
    CONNECTED = "CONNECTED"
    CALL_ENDED = "CALL_ENDED"
    PENDING_CONSENT = "PENDING_CONSENT"
    REVEALED = "REVEALED"
    CLOSED = "CLOSED"                    # terminal, silent
    ABANDONED = "ABANDONED"              # terminal, silent
    LOCKED_IN = "LOCKED_IN"
    RELEASED = "RELEASED"


#: The legal transitions, as data rather than as scattered `if` statements.
#: Anything not listed here is a bug, and `Encounter.transition_to` says so
#: with the state names in the message.
TRANSITIONS: dict[EncounterState, frozenset[EncounterState]] = {
    EncounterState.PROFILED: frozenset({EncounterState.POOLED}),
    EncounterState.POOLED: frozenset(
        {EncounterState.SELECTED, EncounterState.ABANDONED}
    ),
    EncounterState.SELECTED: frozenset({EncounterState.NOTIFIED}),
    EncounterState.NOTIFIED: frozenset({EncounterState.PENDING_ACCEPT}),
    EncounterState.PENDING_ACCEPT: frozenset(
        {EncounterState.CONNECTED, EncounterState.ABANDONED}
    ),
    # CONNECTED -> ABANDONED is an addition to the diagram in §14, which draws
    # only CONNECTED -> CALL_ENDED. It covers the case the diagram does not:
    # both parties accepted and the voice bridge then failed. The encounter has
    # to end somewhere, and ABANDONED is the honest terminal — the call did not
    # happen. It is also the *safe* one, because ABANDONED is silent, so an
    # outage on our side is indistinguishable from a decline on theirs. Anything
    # else would leak "the other person was willing" through an error message.
    EncounterState.CONNECTED: frozenset(
        {EncounterState.CALL_ENDED, EncounterState.ABANDONED}
    ),
    EncounterState.CALL_ENDED: frozenset({EncounterState.PENDING_CONSENT}),
    EncounterState.PENDING_CONSENT: frozenset(
        {EncounterState.REVEALED, EncounterState.CLOSED}
    ),
    EncounterState.REVEALED: frozenset({EncounterState.LOCKED_IN}),
    EncounterState.LOCKED_IN: frozenset({EncounterState.RELEASED}),
    EncounterState.CLOSED: frozenset(),
    EncounterState.ABANDONED: frozenset(),
    EncounterState.RELEASED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {EncounterState.CLOSED, EncounterState.ABANDONED, EncounterState.RELEASED}
)

#: Terminal states that must be indistinguishable from the outside. Both mean
#: "nothing further happened", and neither may say why.
SILENT_TERMINAL_STATES = frozenset(
    {EncounterState.CLOSED, EncounterState.ABANDONED}
)


class ConsentDecision(StrEnum):
    YES = "yes"
    NO = "no"
    #: The window closed with no answer. Treated exactly as a decline for
    #: eligibility, and — critically — indistinguishably from one by the other
    #: party (INVARIANT 2).
    TIMEOUT = "timeout"


class LockInState(StrEnum):
    ACTIVE = "active"
    QUIET = "quiet"                      # no contact for `lockin_quiet_days`
    RELEASED = "released"


class ConsentStage(StrEnum):
    """Which of the two gates a consent record belongs to."""

    ACCEPT = "accept"                    # pre-call: will you take the call
    REVEAL = "reveal"                    # post-call: may we exchange identities


# ---------------------------------------------------------------------------
# Identity and profile
# ---------------------------------------------------------------------------

UserId = Annotated[str, Field(min_length=1, max_length=64)]


class PrivateIdentity(BaseModel):
    """Everything that identifies a person.

    Deliberately a separate class from `Profile`. `src/safety/guardrails.py`
    treats every string in here as a token that must not appear in any
    user-facing output before a mutual reveal, so the anonymity question has
    exactly one place to look.

    All values are synthetic. There is no real personal data in this repository.
    """

    model_config = ConfigDict(frozen=True)

    display_name: str
    phone: str
    email: str

    def tokens(self) -> tuple[str, ...]:
        """The strings a guardrail scans for."""
        parts = [self.display_name, self.phone, self.email]
        # First names leak as readily as full names, so scan for those too.
        parts.extend(self.display_name.split())
        return tuple({p for p in parts if len(p) >= 3})


class Profile(BaseModel):
    """The matchable, shareable part of a person.

    Excluded by design (§13.1): height, appearance, photographs. A product
    whose central claim is removing judgement-by-photograph cannot filter on
    physical attributes, so there is nowhere to put one.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UserId
    intents: list[Intent] = Field(min_length=1)
    interests: list[str] = Field(default_factory=list, max_length=20)
    values: list[str] = Field(default_factory=list, max_length=10)
    personality: str = ""
    lifestyle: str = ""
    languages: list[str] = Field(default_factory=lambda: ["English"], min_length=1)
    availability_window: list[TimeBucket] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list, max_length=10)
    age_band: Literal["18-24", "25-34", "35-44", "45-54", "55+"] = "25-34"

    @field_validator("interests", "values", "dealbreakers", "languages")
    @classmethod
    def _strip_and_dedupe(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for value in values:
            cleaned = value.strip().lower()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen


class ConsentScope(BaseModel):
    """The explicit list of fields the user permits to be used for matching.

    A field absent from `matchable_fields` may not influence a selection, even
    if it is present on the profile.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UserId
    matchable_fields: list[str] = Field(default_factory=list)
    allow_continuity_notes: bool = True
    allow_conversation_prompts: bool = False   # §13.5 is opt-in
    allow_date_suggestions: bool = True
    #: "Receive calls from Spark". Default on, because the daily call IS the
    #: product — but a person who turns it off must stop receiving them, not
    #: merely stop seeing the button.
    #:
    #: Enforced in `spark-voice.connect_call`, the single place a call can be
    #: created, in exactly the same shape as `both_accepted`: the bridge is
    #: handed permission rather than looking it up, and refuses without it.
    #: Hiding the UI alone would leave a code path that still rings somebody
    #: who asked not to be rung.
    allow_calls: bool = True

    def permits(self, field_name: str) -> bool:
        return field_name in self.matchable_fields


class User(BaseModel):
    """§15 `User`. `identity` is held here but never travels into a view."""

    model_config = ConfigDict(extra="forbid")

    id: UserId
    identity: PrivateIdentity
    profile: Profile
    consent_scope: ConsentScope
    verification_tier: VerificationTier = VerificationTier.PHONE
    blocklist: list[UserId] = Field(default_factory=list)
    lockin_slots: int = Field(default=10, ge=0, le=10)
    #: Stable, non-reversible pseudonym shown in an anonymous encounter. Set by
    #: `src/ids.py`; never derived from the display name.
    handle: str = ""

    @model_validator(mode="after")
    def _ids_agree(self) -> User:
        if self.profile.user_id != self.id:
            raise ValueError(
                f"profile.user_id {self.profile.user_id!r} does not match "
                f"user id {self.id!r} — a profile has been attached to the "
                "wrong user."
            )
        if self.consent_scope.user_id != self.id:
            raise ValueError(
                f"consent_scope.user_id {self.consent_scope.user_id!r} does not "
                f"match user id {self.id!r} — a consent scope has been attached "
                "to the wrong user."
            )
        return self


# ---------------------------------------------------------------------------
# Overlap — coarse cell + time bucket, historical only
# ---------------------------------------------------------------------------


class Overlap(BaseModel):
    """Two people were in the same coarse cell in the same time bucket, on a
    day that has already happened.

    INVARIANT 3: `cell_id` is an opaque token. It has no coordinate, no name,
    no size and no neighbour relation exposed anywhere, and it never reaches a
    view. It exists so the Match Agent can prefer people whose routines
    genuinely intersect, and for nothing else.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_a: UserId
    user_b: UserId
    cell_id: str
    time_bucket: TimeBucket
    date: Date

    @model_validator(mode="after")
    def _ordered_and_distinct(self) -> Overlap:
        if self.user_a == self.user_b:
            raise ValueError("an overlap needs two different users")
        if self.user_a > self.user_b:
            raise ValueError(
                "overlap users must be stored in sorted order (user_a < user_b) "
                "so that a pair has exactly one representation"
            )
        return self

    @property
    def pair(self) -> tuple[str, str]:
        return (self.user_a, self.user_b)


# ---------------------------------------------------------------------------
# Encounter, consent, lock-in
# ---------------------------------------------------------------------------


class Consent(BaseModel):
    """§15 `Consent`. Append-only (INVARIANT 5).

    `src/safety/consent.py` owns the ledger and is the only module permitted to
    read these records. They are never joined into anything user-visible.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    encounter_id: str
    user_id: UserId
    stage: ConsentStage
    decision: ConsentDecision
    timestamp: datetime


class Encounter(BaseModel):
    """§15 `Encounter` — the unit of state, alongside `LockIn` (§11.1)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    match_id: str
    day: Date
    user_a: UserId
    user_b: UserId
    state: EncounterState = EncounterState.PROFILED
    #: Who has accepted the *call*. Never rendered — a count is a signal.
    accepted: list[UserId] = Field(default_factory=list)
    call_started: datetime | None = None
    call_ended: datetime | None = None
    call_duration_s: int | None = None
    trace_id: str = ""
    #: Set only when the encounter reached a mutual reveal.
    revealed: bool = False

    def participants(self) -> tuple[str, str]:
        return (self.user_a, self.user_b)

    def other(self, user_id: str) -> str:
        if user_id == self.user_a:
            return self.user_b
        if user_id == self.user_b:
            return self.user_a
        raise ValueError(
            f"user {user_id!r} is not in encounter {self.id!r} "
            f"(participants: {self.user_a}, {self.user_b})"
        )

    def transition_to(self, new_state: EncounterState) -> None:
        """Move to `new_state`, or refuse with a message naming both states.

        The state machine is enforced here rather than trusted to the graph, so
        a node that returns the wrong state fails loudly at the boundary
        instead of quietly corrupting an encounter that spans weeks.
        """
        allowed = TRANSITIONS[self.state]
        if new_state not in allowed:
            legal = ", ".join(sorted(s.value for s in allowed)) or "nothing (terminal)"
            raise ValueError(
                f"illegal encounter transition {self.state.value} -> "
                f"{new_state.value} for encounter {self.id}. "
                f"Legal from {self.state.value}: {legal}. "
                "See docs/ARCHITECTURE.md §14."
            )
        self.state = new_state


class LockIn(BaseModel):
    """§15 `LockIn`. Long-lived: this is the object that makes the
    "plans, acts and adapts over time" claim true."""

    model_config = ConfigDict(extra="forbid")

    id: str
    pair_id: str
    user_a: UserId
    user_b: UserId
    opened_at: datetime
    last_contact: datetime
    #: Days the pair prefer between contacts. Learned by the Continuity Agent
    #: from observed behaviour, not asked for in a form.
    pace_pref_days: float = 3.0
    state: LockInState = LockInState.ACTIVE
    contacts: int = 0
    met_in_person_on: Date | None = None
    released_on: Date | None = None

    def other(self, user_id: str) -> str:
        if user_id == self.user_a:
            return self.user_b
        if user_id == self.user_b:
            return self.user_a
        raise ValueError(f"user {user_id!r} is not in lock-in {self.id!r}")


class ContinuityNote(BaseModel):
    """§15 `Continuity`. What the pair actually discussed.

    Scoped per user, deletable on request, and never surfaced to anyone the
    note was not about — `src/mcp/services.py` enforces the scope on read.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    lockin_id: str
    #: The user this note belongs to. A note is readable only by this user's
    #: own agent runs.
    owner_id: UserId
    note: str
    source: Literal["call", "message", "meeting", "system"] = "call"
    created_at: datetime
    expires_at: datetime


class Outcome(BaseModel):
    """§15 `Outcome`. Private signals, never rendered to the other party.

    `prediction_error` is what lets us ask whether the Match Agent knew
    anything: predicted confidence minus what actually happened.
    """

    model_config = ConfigDict(extra="forbid")

    encounter_id: str | None = None
    lockin_id: str | None = None
    private_signals: dict[str, float] = Field(default_factory=dict)
    prediction_error: float | None = None

    @model_validator(mode="after")
    def _one_subject(self) -> Outcome:
        if (self.encounter_id is None) == (self.lockin_id is None):
            raise ValueError(
                "an Outcome attaches to exactly one of encounter_id or lockin_id"
            )
        return self
