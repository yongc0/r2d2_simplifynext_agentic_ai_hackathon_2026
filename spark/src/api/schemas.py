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
    #: Which of the three offers this is. A category describing the PLAN, never
    #: a claim about the people.
    shape: str = "easy"
    budget_band: str = Field(default="flexible", serialization_alias="budgetBand")
    duration_band: str = Field(default="two_hours", serialization_alias="durationBand")


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


# ---------------------------------------------------------------------------
# Date Studio
# ---------------------------------------------------------------------------
#
# INVARIANT 1 NOTE: nothing below has a field for an address, a coordinate, a
# cell, a distance or a map, and nothing may gain one. Date plans are the only
# thing in Spark allowed to point somewhere, and they are safe only because the
# ranking behind them cannot read a location.


class DatePreferencesOut(BaseModel):
    """The saved constraints, plus what the form may offer.

    `sharedBuckets` comes from the server because a time only one of them is
    free is not a choice — offering it would produce a plan neither can attend.
    """

    model_config = ConfigDict(populate_by_name=True)

    mood: str | None = None
    budget: str | None = None
    duration: str | None = None
    energy: str | None = None
    formats: list[str] = Field(default_factory=list)
    time_bucket: str | None = Field(default=None, serialization_alias="timeBucket")
    shared_buckets: list[str] = Field(
        default_factory=list, serialization_alias="sharedBuckets"
    )
    #: True when these values came from memory rather than from this session, so
    #: the form can say it prefilled them instead of pretending the person did.
    prefilled: bool = False


class DatePreferencesIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    mood: str | None = None
    budget: str | None = None
    duration: str | None = None
    energy: str | None = None
    formats: list[str] = Field(default_factory=list, max_length=5)
    time_bucket: str | None = Field(default=None, alias="timeBucket")
    #: OPT-IN. Tonight's mood is not a durable preference unless asked for.
    remember: bool = False
    #: Which of the three offered plans to turn into a real itinerary. Omitted
    #: by "Plan the Date" — with no path named, the best-ranked one is used,
    #: which is the whole point of a one-tap button.
    path_id: str | None = Field(default=None, alias="pathId")


class DateMemoryOut(BaseModel):
    """One remembered preference, as the memory panel shows it."""

    model_config = ConfigDict(populate_by_name=True)

    memory_id: str = Field(serialization_alias="memoryId")
    scope: Literal["user", "lockin"]
    lockin_id: str | None = Field(default=None, serialization_alias="lockInId")
    dimension: str
    value: str
    #: "explicit" or "feedback" — shown, because a person should be able to see
    #: the difference between what they told Spark and what it inferred.
    source: str
    confidence: float
    updated_at: str = Field(serialization_alias="updatedAt")


class DateMemoryPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=64)


class DateFeedbackIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    action: Literal["saved", "rejected", "completed"]
    reasons: list[str] = Field(default_factory=list, max_length=8)


class PlanLockInOut(BaseModel):
    """A connection you can plan with, for the `/plans` hub."""

    model_config = ConfigDict(populate_by_name=True)

    lock_in_id: str = Field(serialization_alias="lockInId")
    person: RevealOut
    state: Literal["active", "quiet", "released"]
    #: Present and non-null only when planning is NOT available, so the hub can
    #: say why rather than showing a dead button.
    unavailable_reason: str | None = Field(
        default=None, serialization_alias="unavailableReason"
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsOut(BaseModel):
    """The switches a person controls.

    Each maps to a field on `ConsentScope`, which is the thing the agents
    actually consult — so a setting shown here is a setting that is enforced,
    not a preference the interface remembers on its own.
    """

    model_config = ConfigDict(populate_by_name=True)

    #: "Receive calls from Spark". Enforced in `spark-voice.connect_call`, the
    #: single place a call can be created — not by hiding a button.
    allow_calls: bool = Field(serialization_alias="allowCalls")
    allow_date_suggestions: bool = Field(serialization_alias="allowDateSuggestions")
    allow_continuity_notes: bool = Field(serialization_alias="allowContinuityNotes")
    allow_conversation_prompts: bool = Field(
        serialization_alias="allowConversationPrompts"
    )


class SettingsIn(BaseModel):
    """A partial update. Anything omitted is left alone."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    allow_calls: bool | None = Field(default=None, alias="allowCalls")
    allow_date_suggestions: bool | None = Field(
        default=None, alias="allowDateSuggestions"
    )
    allow_continuity_notes: bool | None = Field(
        default=None, alias="allowContinuityNotes"
    )
    allow_conversation_prompts: bool | None = Field(
        default=None, alias="allowConversationPrompts"
    )


# ---------------------------------------------------------------------------
# Itineraries — the plan with real venues, times and a route
# ---------------------------------------------------------------------------
#
# These carry addresses and coordinates, which nothing else in this file does.
# That is permitted only here and only post-reveal: see `ARCHITECTURE.md` §13.6
# and the module docstring of `src/schemas/itinerary.py`. Every one of these
# fields describes a DESTINATION two people chose together, never a place either
# of them has been.


class TravelLegOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    minutes: int
    metres: int
    mode: str
    #: Always true, and rendered. An estimate that looks measured is the kind of
    #: small dishonesty that makes somebody miss a booking.
    estimated: bool = True
    detail: str = ""


class ItineraryStopOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stop_id: str = Field(serialization_alias="stopId")
    order: int
    activity_type: str = Field(serialization_alias="activityType")
    venue_id: str = Field(serialization_alias="venueId")
    venue_name: str = Field(serialization_alias="venueName")
    #: `null` renders as "address not listed", never as a guess.
    address: str | None = None
    lat: float
    lon: float
    start_time: str = Field(serialization_alias="startTime")
    end_time: str = Field(serialization_alias="endTime")
    duration_minutes: int = Field(serialization_alias="durationMinutes")
    estimated_cost: str = Field(serialization_alias="estimatedCost")
    cost_band: str = Field(serialization_alias="costBand")
    rationale: str
    travel_from_previous: TravelLegOut | None = Field(
        default=None, serialization_alias="travelFromPrevious"
    )
    maps_url: str = Field(serialization_alias="mapsUrl")
    #: "open" | "closed" | "unknown". The client renders all three differently;
    #: unknown must never be styled as open.
    opening_state: str = Field(serialization_alias="openingState")
    opening_hours: str | None = Field(
        default=None, serialization_alias="openingHours"
    )
    opening_detail: str = Field(default="", serialization_alias="openingDetail")
    is_commercial_partner: bool = Field(
        default=False, serialization_alias="isCommercialPartner"
    )


class ItineraryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    itinerary_id: str = Field(serialization_alias="itineraryId")
    lock_in_id: str = Field(serialization_alias="lockInId")
    path_id: str = Field(serialization_alias="pathId")
    headline: str
    time_bucket: str = Field(serialization_alias="timeBucket")
    day_label: str = Field(serialization_alias="dayLabel")
    stops: list[ItineraryStopOut] = Field(default_factory=list)
    total_duration_minutes: int = Field(serialization_alias="totalDurationMinutes")
    total_cost_estimate: str = Field(serialization_alias="totalCostEstimate")
    grounded_in: list[str] = Field(serialization_alias="groundedIn")
    status: str
    note: str = ""
    #: A licence condition. Any surface rendering these venues shows it.
    attribution: str = "© OpenStreetMap contributors"
    updated_at: str = Field(serialization_alias="updatedAt")
    #: Whether THIS viewer has already written a reflection. Never whether the
    #: other person has — that is the whole point of a private reflection.
    has_reflection: bool = Field(default=False, serialization_alias="hasReflection")


class ItineraryResultOut(BaseModel):
    """An itinerary, or a stated reason there is not one.

    A single shape for both outcomes so the client cannot accidentally render an
    empty plan as a plan. `unavailable` distinguishes "we have no venue data"
    from "nothing that fits is open then" — §12 asks for both states, and they
    are different facts about the world.
    """

    model_config = ConfigDict(populate_by_name=True)

    itinerary: ItineraryOut | None = None
    #: Present only when `itinerary` is null.
    reason: str = ""
    #: True when the cause is missing venue data rather than an empty result.
    data_unavailable: bool = Field(
        default=False, serialization_alias="dataUnavailable"
    )


class ItineraryStatusIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    #: One of `USER_SETTABLE_STATUSES`. `draft` and `completed` are not a
    #: person's to set — the planner owns one and the clock owns the other.
    status: str


class ReflectionIn(BaseModel):
    """The post-date form.

    PRIVATE. There is no route that returns this to anybody but its author, and
    no field here names the other person.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    overall: int = Field(ge=1, le=5)
    #: Optional per aspect: somebody who only wants to leave an overall rating
    #: must be able to. Keys are `ReflectionAspect`; values 1-5.
    ratings: dict[str, int] = Field(default_factory=dict)
    second_date: str = Field(alias="secondDate")
    notes: str = Field(default="", max_length=2000)


class ReflectionOut(BaseModel):
    """A reflection, shown back to the person who wrote it. Nobody else."""

    model_config = ConfigDict(populate_by_name=True)

    reflection_id: str = Field(serialization_alias="reflectionId")
    itinerary_id: str = Field(serialization_alias="itineraryId")
    lock_in_id: str = Field(serialization_alias="lockInId")
    overall: int
    ratings: dict[str, int] = Field(default_factory=dict)
    second_date: str = Field(serialization_alias="secondDate")
    notes: str = ""
    created_at: str = Field(serialization_alias="createdAt")
    #: Said in the interface, every time: what this is used for and what it is
    #: not. A privacy promise nobody is shown is not a privacy promise.
    privacy_note: str = Field(
        default=(
            "Only you can see this. It is never shown to the person you met, "
            "and they are never told whether you filled it in."
        ),
        serialization_alias="privacyNote",
    )


class PlacesStatusOut(BaseModel):
    """Whether real venue data is loaded. Drives the §12 unavailable state."""

    model_config = ConfigDict(populate_by_name=True)

    available: bool
    count: int
    with_hours: int = Field(serialization_alias="withHours")
    source: str
    attribution: str
    note: str


class ProfileOut(BaseModel):
    """The editable half of a person's own profile.

    Their OWN. This model is only ever built for the viewer, and there is no
    route that returns it for anybody else — a matchable profile is exactly the
    thing the product refuses to let people browse.

    Note what is absent and must stay absent (§13.1): height, appearance, and
    anything photographic. The product's central claim is that it removes
    judgement-by-photograph, so there is nowhere to put one.
    """

    model_config = ConfigDict(populate_by_name=True)

    intents: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    personality: str = ""
    lifestyle: str = ""
    languages: list[str] = Field(default_factory=list)
    availability_window: list[str] = Field(
        default_factory=list, serialization_alias="availabilityWindow"
    )
    #: Which time buckets this person has ever actually been out in. Offered as
    #: the choices for availability, because a window nobody is ever free in is
    #: a preference that quietly removes them from every pool.
    known_buckets: list[str] = Field(
        default_factory=list, serialization_alias="knownBuckets"
    )


class ProfileIn(BaseModel):
    """A partial update. Anything omitted is left alone.

    THIS IS NOT A UI-ONLY FORM. What it writes is the same `Profile` the Match
    Agent reads: intents gate eligibility, interests decide overlap scoring and
    every date plan's grounding, and the availability window decides which
    encounter slots this person can be offered at all. Changing something here
    changes who Spark suggests, not just what the screen says.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    intents: list[str] | None = None
    interests: list[str] | None = Field(default=None, max_length=20)
    values: list[str] | None = Field(default=None, max_length=10)
    personality: str | None = Field(default=None, max_length=280)
    lifestyle: str | None = Field(default=None, max_length=280)
    languages: list[str] | None = None
    availability_window: list[str] | None = Field(
        default=None, alias="availabilityWindow"
    )
