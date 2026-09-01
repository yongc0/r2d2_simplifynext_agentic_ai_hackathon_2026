"""A date plan that a person could actually follow.

`DatePath` says WHAT KIND of evening ("a gallery, then somewhere to eat").
`DateItinerary` says WHERE, WHEN, HOW LONG and HOW YOU GET BETWEEN THEM. It is
the same evening bound to real venues, real coordinates and real clock times —
one coherent plan rather than a list of unrelated suggestions.

The split is deliberate and it is what keeps invariant 3 intact. The RANKING
happens on `DatePath`, where no location field exists and none can be read; the
BINDING to a real venue happens afterwards, from a catalogue that was never told
where either person is. A plan cannot become "near where you both were" because
nothing in the chain that chooses it can see a person's whereabouts.

WHAT THIS MODULE REFUSES TO REPRESENT

There is no field for a venue rating, a review count, a popularity score or a
"recommended" flag. Spark has not visited these places. The data is
OpenStreetMap's — names, coordinates and, where somebody contributed them,
opening hours — and presenting it as a curated recommendation would be a claim
we cannot support.

`opening_state` has three values and the third is the important one. UNKNOWN is
not a soft "probably open": OpenStreetMap's hours coverage is patchy, and the
one outcome worth engineering against is two people standing outside a locked
door because a planner filled in a blank.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.core import TimeBucket
from src.schemas.date_studio import Budget

#: Where an itinerary is in its life. Draft is ours; everything after it is
#: something a person did.
#:
#: There is no "rejected by them" status, and there must not be one. A plan the
#: other person did not accept is `cancelled`, exactly like one nobody got round
#: to — invariant 2's rule, applied past the reveal: the interface must not be
#: able to tell somebody they were turned down.
ItineraryStatus = Literal[
    "draft",       # generated, not yet sent to the other person
    "proposed",    # shared with them, waiting
    "confirmed",   # both said yes
    "completed",   # the date happened
    "cancelled",   # called off, or it simply never happened
]

#: Statuses a user may set. `draft` is the planner's, and `completed` is set by
#: the clock rather than by a button — a person cannot mark a future date done.
USER_SETTABLE_STATUSES: tuple[str, ...] = ("proposed", "confirmed", "cancelled")

#: When a bucket starts, for laying out clock times. Coarse on purpose: these
#: are the same buckets overlap uses, and pretending to know that somebody is
#: free at 18:40 rather than "the evening" would be inventing precision.
BUCKET_START_HOUR: dict[str, int] = {
    "early_morning": 7,
    "morning": 9,
    "midday": 12,
    "afternoon": 15,
    "evening": 18,
    "night": 21,
}

#: A stop's length, by the duration band the plan was ranked under. Whole hours
#: because the estimate does not deserve minutes.
STOP_MINUTES: dict[str, int] = {
    "one_hour": 60,
    "two_hours": 75,
    "whole_evening": 105,
}

#: What a band costs per person, as a sentence rather than a number. Spark does
#: not know these venues' prices — the band came from the venue's CATEGORY —
#: so a dollar figure would be a fabrication with a decimal point on it.
COST_TEXT: dict[str, str] = {
    "free": "Free",
    "under_20": "Around $10-20 each",
    "under_50": "Around $20-50 each",
    "flexible": "Varies",
}


class TravelLeg(BaseModel):
    """How you get from the previous stop to this one.

    `estimated` is `True` and is not permitted to be anything else — see the
    field type. This is straight-line distance over a walking speed, not a
    routed journey, and every surface that renders it says so. A travel time
    that looks measured when it is arithmetic is the kind of small dishonesty
    that makes someone miss a booking.
    """

    model_config = ConfigDict(extra="forbid")

    minutes: int = Field(ge=1, le=180)
    metres: int = Field(ge=0)
    mode: Literal["walking", "transit"]
    estimated: Literal[True] = True
    detail: str = "Straight-line estimate, not a routed journey."


class ItineraryStop(BaseModel):
    """One place, at one time, in one plan.

    Everything the requirement asks for — activity, venue, address, start and
    end, duration, cost, travel time, and why this one — and nothing that would
    let it be read as an endorsement.
    """

    model_config = ConfigDict(extra="forbid")

    stop_id: str
    #: 1-based, and contiguous. The map's numbered markers are these.
    order: int = Field(ge=1, le=6)
    activity_type: Literal["activity", "food", "drink"]

    venue_id: str
    venue_name: str = Field(min_length=1, max_length=160)
    #: OpenStreetMap frequently has no address for a node that has a name and a
    #: coordinate. `None` renders as "address not listed" — never as a guess
    #: assembled from the surrounding streets.
    address: str | None = None
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)

    #: "18:00". Local clock, no timezone: the plan is for two people in one
    #: city on one evening, and an ISO instant would imply a precision the
    #: bucket it came from does not have.
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    duration_minutes: int = Field(ge=15, le=300)

    estimated_cost: str = Field(min_length=1, max_length=60)
    cost_band: Budget

    #: Why THIS venue, in the plan's own words. Grounded in the shared
    #: interests the path was built from.
    rationale: str = Field(min_length=1, max_length=240)

    #: `None` on the first stop, and only there — enforced by the itinerary.
    travel_from_previous: TravelLeg | None = None

    #: Keyless directions link. See `places.maps_url`.
    maps_url: str = Field(min_length=1)

    opening_state: Literal["open", "closed", "unknown"]
    #: As contributed to OpenStreetMap, verbatim, or `None` when nobody has.
    opening_hours: str | None = None
    opening_detail: str = ""

    #: Mandatory, as on every other Spark model that can render a venue: a
    #: partner cannot be constructed without its label.
    is_commercial_partner: bool = False

    @model_validator(mode="after")
    def _a_closed_venue_is_not_a_stop(self) -> "ItineraryStop":
        if self.opening_state == "closed":
            raise ValueError(
                f"{self.venue_name!r} is closed at {self.start_time}; a stop "
                "that cannot be visited must be dropped or re-timed by the "
                "planner, not rendered with a warning beside it"
            )
        return self


class DateItinerary(BaseModel):
    """One evening, in order, with times.

    The unit the whole planner produces and the whole interface renders. A user
    accepts, edits, replaces a stop in, or cancels ONE of these — not a bag of
    suggestions they have to assemble themselves.
    """

    model_config = ConfigDict(extra="forbid")

    itinerary_id: str
    lockin_id: str
    #: The `DatePath` this was bound from, so a plan can be traced back to the
    #: ranking that chose its shape.
    path_id: str
    #: Set from the session. Never accepted from a client — the same rule as
    #: `DateMemoryItem.owner_id`, and for the same reason.
    owner_id: str

    headline: str = Field(min_length=1, max_length=200)
    time_bucket: TimeBucket
    #: "Saturday", "Tomorrow". A label, not a date: nothing here has agreed a
    #: calendar day with anybody, and printing one would imply it had.
    day_label: str = Field(min_length=1, max_length=40)

    stops: list[ItineraryStop] = Field(min_length=1, max_length=4)

    #: Everything including the walks between. Derived, never supplied.
    total_duration_minutes: int = Field(ge=15, le=720)
    total_cost_estimate: str = Field(min_length=1, max_length=80)

    #: Interests BOTH people listed. Empty is not allowed, exactly as on
    #: `DatePath`: an ungrounded plan is a guess with an address attached.
    grounded_in: list[str] = Field(min_length=1)

    status: ItineraryStatus = "draft"
    #: Said out loud whenever something is missing or uncertain, rather than
    #: quietly leaving a gap.
    note: str = ""
    #: A licence condition, not a courtesy. Anything rendering these venues
    #: shows it.
    attribution: str = "© OpenStreetMap contributors"

    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _stops_are_ordered_and_travel_is_between(self) -> "DateItinerary":
        for index, stop in enumerate(self.stops):
            if stop.order != index + 1:
                raise ValueError(
                    f"stop {stop.stop_id} claims order {stop.order} but sits at "
                    f"position {index + 1}; the map's numbered markers read this "
                    "field, so a mismatch sends somebody to the wrong place first"
                )
            if index == 0 and stop.travel_from_previous is not None:
                raise ValueError(
                    "the first stop cannot have travel from a previous one"
                )
            if index > 0 and stop.travel_from_previous is None:
                raise ValueError(
                    f"stop {stop.stop_id} has no travel leg; a plan that does "
                    "not say how long it takes to get there is not an itinerary"
                )
        return self


# ---------------------------------------------------------------------------
# After the date
# ---------------------------------------------------------------------------

#: 1-5, on the things a person can actually judge about an evening.
ReflectionAspect = Literal[
    "conversation",
    "location",
    "activity",
    "vibe",
    "comfort",
]

SecondDate = Literal["yes", "maybe", "no"]

#: The two aspects that describe the PLAN rather than the person.
#:
#: `conversation`, `vibe` and `comfort` are absent, on purpose. They are the
#: most important things on the form and the least usable as signal: a quiet
#: conversation is not evidence that the venue was wrong, and a recommender that
#: treats "we did not click" as "book somewhere louder" is inventing a
#: preference out of a feeling. They are recorded for the person who wrote them
#: and read by nothing else.
PLAN_ASPECTS: tuple[str, ...] = ("location", "activity")

#: A reflection this good says the shape of the evening worked.
GOOD_ENOUGH = 4

#: A rating this low says it did not.
POOR = 2

class DateReflection(BaseModel):
    """How the date went, for the person who was on it.

    PRIVATE, AND STRUCTURALLY SO. There is no field here that names the other
    person, no API that returns another user's reflection, and no aggregate
    anywhere that could be differenced back to one. The other party is never
    told this exists, never told it was filled in, and never told what it said.

    That is not a display rule. `second_date` is the reason: a person who says
    "no" must be able to say it honestly, and the only way that is safe is if
    the other person can never learn it — not from a screen, not from a silence
    that started the moment the form was submitted, not from a "they have moved
    on" nudge. Nothing downstream of this model may branch on `second_date` in a
    way the other party could observe.

    HOW THIS SITS WITH "SPARK DOES NOT GRADE YOUR DATES"

    `DatePlanFeedback` is about the recommendation and is deliberately not
    allowed to ask whether an evening went well. This model does ask, and the
    difference is who reads the answer. Feedback tunes what Spark offers you.
    A reflection is yours: it is shown back to you, it can be deleted, and only
    the two aspects in `ASPECT_TO_DIMENSION` — which are about the PLACE and the
    ACTIVITY, not about the person — ever reach the recommender. No score about
    a human being is stored, ranked or shown to anybody.
    """

    model_config = ConfigDict(extra="forbid")

    reflection_id: str
    itinerary_id: str
    lockin_id: str
    #: From the session. Whose reflection this is; also whose eyes it is for.
    owner_id: str

    overall: int = Field(ge=1, le=5)
    #: Optional per aspect — somebody who only wants to give an overall star
    #: rating must be able to.
    ratings: dict[ReflectionAspect, int] = Field(default_factory=dict)
    second_date: SecondDate
    #: Free text, for the things the stars cannot hold. Never parsed, never
    #: shown to anyone else, never turned into a preference: interpreting it is
    #: exactly where a recommender starts inventing.
    notes: str = Field(default="", max_length=2000)

    created_at: datetime
    #: Soft delete, so "forget this" leaves an audit trail rather than a hole.
    active: bool = True

    @model_validator(mode="after")
    def _ratings_are_in_range(self) -> "DateReflection":
        for aspect, value in self.ratings.items():
            if not 1 <= value <= 5:
                raise ValueError(f"rating {value} for {aspect!r} is outside 1-5")
        return self

    def planning_signal(self) -> tuple[str, list[str]] | None:
        """What, if anything, this tells the recommender. Often nothing.

        Returns a `(FeedbackAction, RejectionReason[])` pair in Date Studio's
        existing vocabulary, so a reflection joins the same auditable feedback
        trail as a thumbs-down on a plan. There is no second learning mechanism
        and no new kind of belief — one path in, one place to inspect.

        WHY THE NEGATIVE SIGNAL IS DELIBERATELY VAGUE

        A venue rated 1 out of 5 says the choice was wrong. It does not say
        whether it was too loud, too dear or too far, and the honest reason for
        that is `not_our_style` — which the scorer records and pointedly does
        NOT turn into a direction. Picking one anyway ("rated the bar badly, so
        prefer quiet") would be a preference manufactured from a shrug, and the
        person would never see where it came from.

        A 3 out of 5 returns `None`. A middling evening is not evidence of
        anything, and a recommender that moves on one is learning noise.
        """
        poor = [
            aspect
            for aspect in PLAN_ASPECTS
            if (self.ratings.get(aspect) or 0) and self.ratings[aspect] <= POOR  # type: ignore[index]
        ]
        if poor:
            return ("rejected", ["not_our_style"])
        if self.overall >= GOOD_ENOUGH:
            # They went, and it worked. The strongest honest endorsement of a
            # plan's shape there is — and note it reads `overall`, never
            # `second_date`: whether they want to see the person again is not a
            # verdict on where Spark sent them.
            return ("completed", [])
        return None
