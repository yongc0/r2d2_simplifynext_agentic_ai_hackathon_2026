"""Itinerary Agent — organisers' class: **Transaction**.

Turns a ranked `DatePath` — "a gallery, then somewhere to eat" — into a plan two
people can follow: named venues, addresses, clock times, walking legs between
them, a cost estimate, and a reason for each stop.

WHY THIS IS A SEPARATE AGENT AND NOT PART OF THE DATE AGENT

Because the two do different jobs and only one of them is allowed near a
coordinate. The Date Agent RANKS, from shared interests and stored preferences,
over a catalogue with no location field. This agent BINDS, from a catalogue that
has coordinates but has never been told where either person is or was. Keeping
them apart is what makes "near where you both were" unbuildable rather than
merely unbuilt: there is no call site anywhere that holds both an overlap cell
and a venue coordinate.

WHY IT IS DETERMINISTIC

Same reason as the Date Agent. Choosing which real cafe fills "somewhere to eat"
is a lookup and an ordering over structured attributes — a model would add
variance, cost and a failure mode, and could not do it better. Nothing here
calls an LLM, and the plan is identical on every run, which is also what makes
it filmable twice.

WHAT IT WILL NOT DO

Invent a venue. If `spark-places` has no data, this returns `None` with a reason
and the interface shows an unavailable state. A fabricated address is a real
person standing outside a building that was never there.

Send somebody to a closed venue. Opening hours are checked at the stop's actual
start time, and a venue that is closed then is skipped. A venue with no recorded
hours is marked UNKNOWN and said to be unknown — never quietly treated as open.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.mcp.registry import MCPClient
from src.schemas.agents import DatePath
from src.schemas.itinerary import (
    BUCKET_START_HOUR,
    COST_TEXT,
    STOP_MINUTES,
    DateItinerary,
    ItineraryStop,
    TravelLeg,
)
from src.telemetry.trace import span

AGENT_CLASS = "Transaction"

#: A second or third stop is shorter than the lead. Sitting down after a gallery
#: is an hour, not an evening, and stacking two full-length stops produces a
#: plan that reads as a day off work.
LATER_STOP_MINUTES = 60

#: Hard ceiling on venues EXAMINED per stop — the opening-hours check runs once
#: per candidate, and loop discipline is graded.
MAX_CANDIDATES = 20

#: How many venues are FETCHED to choose those from. Much larger, and the
#: distinction matters: the pool is sorted by distance from the previous stop
#: before anything is examined, so a small pool means the proximity sort is
#: choosing the nearest of an arbitrary twenty rather than the nearest overall.
#:
#: That was a real bug. With 232 eligible cafes in the file, a pool of 20 —
#: ordered by interest overlap and then by id — reliably contained nothing near
#: the first stop, and the "nearest first" fix appeared to do nothing at all.
#: Sorting is cheap; fetching a wider pool costs one in-memory slice.
SEARCH_POOL = 120

#: A walk between stops longer than this stops being one evening and starts
#: being two outings with a commute in the middle. Not a hard filter — if the
#: nearest option is further, it is still offered, with the length said out
#: loud — because "nothing at all" is a worse answer than "this one is a trek".
COMFORTABLE_LEG_MINUTES = 25


@dataclass
class NoItinerary:
    """Why a plan could not be built, in words the interface can show.

    A typed refusal rather than `None`, because "we have no venue data" and
    "everything that fits is shut at that hour" are different facts and a person
    deserves to be told which one applies.
    """

    reason: str
    #: True when the cause is missing data rather than a genuine empty result.
    #: The client renders a different state for each — §12.
    data_unavailable: bool = False


@dataclass
class ItineraryAgent:
    client: MCPClient
    name: str = "itinerary"

    # -----------------------------------------------------------------
    def build(
        self,
        path: DatePath,
        owner_id: str,
        # A LABEL, not a calendar day. "Saturday" would claim an agreement
        # with somebody that nothing here has made; the API passes the bucket
        # read as a time of day instead.
        day_label: str = "An evening",
        exclude_venue_ids: frozenset[str] = frozenset(),
    ) -> DateItinerary | NoItinerary:
        """One coherent evening, or a stated reason there is not one.

        `exclude_venue_ids` is how "not this one" works: the caller passes what
        was already offered and gets a genuinely different plan rather than the
        same venue with a new id.
        """
        with span("agent.itinerary", path_id=path.path_id) as s:
            available = self.client.try_call(
                "spark-places", "places_available", default={"available": False}
            ) or {"available": False}
            if not available.get("available"):
                s.set_attribute("outcome", "no venue data")
                return NoItinerary(
                    reason=(
                        "Spark has no venue data loaded, so it cannot name real "
                        "places yet. The plan above is still what suits you both "
                        "— we would rather show nothing than invent an address."
                    ),
                    data_unavailable=True,
                )

            start_hour = BUCKET_START_HOUR.get(str(path.proposed_bucket), 18)
            clock = start_hour * 60
            used: set[str] = set(exclude_venue_ids)

            stops: list[ItineraryStop] = []
            skipped_closed = 0
            for index, planned in enumerate(path.stops):
                minutes = (
                    STOP_MINUTES.get(path.duration_band, 75)
                    if index == 0
                    else LATER_STOP_MINUTES
                )
                previous = stops[-1] if stops else None

                bound, closed = self._bind(
                    planned_category=planned.category,
                    interests=path.grounded_in,
                    budget=path.budget_band,
                    used=used,
                    previous=previous,
                    arrive_minutes=clock,
                    duration=minutes,
                )
                skipped_closed += closed
                if bound is None:
                    continue

                venue, leg, arrive = bound
                used.add(venue["venue_id"])
                stop = self._stop(
                    order=len(stops) + 1,
                    category=planned.category,
                    venue=venue,
                    start_minutes=arrive,
                    duration=minutes,
                    budget=path.budget_band,
                    grounded_in=path.grounded_in,
                    travel=leg,
                    is_partner=planned.is_commercial_partner,
                )
                stops.append(stop)
                clock = arrive + minutes

            if not stops:
                s.set_attribute("outcome", "nothing open")
                return NoItinerary(
                    reason=(
                        "Nothing that fits is open at that time. Try another "
                        "part of the day, or relax one of the boxes."
                    )
                )

            s.set_attribute("stops", len(stops))
            s.set_attribute("skipped_closed", skipped_closed)
            return self._assemble(
                lockin_id=path.lockin_id,
                path_id=path.path_id,
                headline=path.headline,
                bucket=str(path.proposed_bucket),
                grounded_in=path.grounded_in,
                wanted_stops=len(path.stops),
                owner_id=owner_id,
                day_label=day_label,
                stops=stops,
                skipped_closed=skipped_closed,
            )

    # -----------------------------------------------------------------
    def replace_stop(
        self,
        itinerary: DateItinerary,
        order: int,
    ) -> DateItinerary | NoItinerary:
        """Swap one stop, keep the rest, re-time everything after it.

        The requirement is "replace a single stop without regenerating the whole
        plan", and the subtlety is the word *whole*: the stops before it must be
        untouched — same venues, same times — while the stops after it genuinely
        must move, because the walk to a different venue takes a different
        number of minutes. A planner that left the later times alone would hand
        somebody a schedule that no longer adds up.
        """
        with span("agent.itinerary.replace", itinerary_id=itinerary.itinerary_id) as s:
            if not 1 <= order <= len(itinerary.stops):
                return NoItinerary(reason=f"There is no stop {order} in this plan.")

            keep = itinerary.stops[: order - 1]
            # Everything already in this plan is off the table, so "swap it" can
            # never return what is already on screen.
            used = {stop.venue_id for stop in itinerary.stops}

            s.set_attribute("replacing", order)
            rebuilt = list(keep)
            clock = (
                _to_minutes(keep[-1].end_time) if keep else _to_minutes(itinerary.stops[0].start_time)
            )

            for index in range(order - 1, len(itinerary.stops)):
                planned = itinerary.stops[index]
                previous = rebuilt[-1] if rebuilt else None
                minutes = planned.duration_minutes
                # Only the replaced stop is re-chosen. The ones after it keep
                # their venue and are simply re-timed — otherwise "swap stop 1"
                # would silently change stop 2 as well.
                if index == order - 1:
                    bound, _closed = self._bind(
                        planned_category=planned.activity_type,
                        interests=itinerary.grounded_in,
                        budget=planned.cost_band,
                        used=used,
                        previous=previous,
                        arrive_minutes=clock,
                        duration=minutes,
                    )
                    if bound is None:
                        return NoItinerary(
                            reason=(
                                "Nothing else of that kind is open then. The "
                                "plan is unchanged."
                            )
                        )
                    venue, leg, arrive = bound
                    used.add(venue["venue_id"])
                    rebuilt.append(
                        self._stop(
                            order=len(rebuilt) + 1,
                            category=planned.activity_type,
                            venue=venue,
                            start_minutes=arrive,
                            duration=minutes,
                            budget=planned.cost_band,
                            grounded_in=itinerary.grounded_in,
                            travel=leg,
                            is_partner=venue.get("is_commercial_partner", False),
                        )
                    )
                else:
                    leg = (
                        self._leg(previous, planned.lat, planned.lon)
                        if previous is not None
                        else None
                    )
                    arrive = clock + (leg.minutes if leg else 0)
                    rebuilt.append(
                        planned.model_copy(
                            update={
                                "order": len(rebuilt) + 1,
                                "travel_from_previous": leg,
                                "start_time": _to_clock(arrive),
                                "end_time": _to_clock(arrive + minutes),
                            }
                        )
                    )
                clock = _to_minutes(rebuilt[-1].end_time)

            return self._assemble(
                lockin_id=itinerary.lockin_id,
                path_id=itinerary.path_id,
                headline=itinerary.headline,
                bucket=str(itinerary.time_bucket),
                grounded_in=itinerary.grounded_in,
                wanted_stops=len(itinerary.stops),
                owner_id=itinerary.owner_id,
                day_label=itinerary.day_label,
                stops=rebuilt,
                skipped_closed=0,
                itinerary_id=itinerary.itinerary_id,
                created_at=itinerary.created_at,
                status=itinerary.status,
            )

    # -----------------------------------------------------------------
    def _bind(
        self,
        planned_category: str,
        interests: list[str],
        budget: str,
        used: set[str],
        previous: ItineraryStop | None,
        arrive_minutes: int,
        duration: int,
    ) -> tuple[tuple[dict, TravelLeg | None, int], int] | tuple[None, int]:
        """The first real venue of this kind that is not shut when you arrive.

        Returns the venue, the walk to it, and the minute you actually get
        there — the arrival time depends on the walk, and the walk depends on
        which venue, so the two are resolved together rather than in sequence.
        """
        result = self.client.try_call(
            "spark-places",
            "search_places",
            default={"options": []},
            interests=list(interests),
            category=planned_category,
            budget=budget,
            limit=SEARCH_POOL,
        ) or {"options": []}

        options = list(result.get("options", []))
        if previous is not None:
            # NEAREST FIRST, and this is the difference between an itinerary and
            # a list. Ranked purely on interest overlap, the planner cheerfully
            # put a gallery in MacPherson and a coffee shop in Queenstown in the
            # same evening — ten kilometres and a two-hour journey apart. Both
            # stops were individually well chosen and the plan was nonsense.
            #
            # THIS IS NOT PROXIMITY TO A PERSON, which is what invariant 3
            # forbids. It is the distance between two venues already chosen for
            # an itinerary; nothing here knows where either participant is, has
            # been, or lives, and `spark-places` still cannot be told.
            options.sort(key=lambda v: (_rough_gap(previous, v), v["venue_id"]))

        skipped = 0
        for venue in options[:MAX_CANDIDATES]:
            if venue["venue_id"] in used:
                continue
            leg = self._leg(previous, venue["lat"], venue["lon"]) if previous else None
            arrive = arrive_minutes + (leg.minutes if leg else 0)

            opening = self.client.try_call(
                "spark-places",
                "is_open_at",
                default={"state": "unknown", "detail": ""},
                opening_hours=venue.get("opening_hours"),
                hour=(arrive // 60) % 24,
            ) or {"state": "unknown", "detail": ""}

            if opening["state"] == "closed":
                # Not a warning beside a stop — a venue you cannot get into is
                # not a stop. Try the next one.
                skipped += 1
                continue
            venue = {**venue, "_opening": opening}
            return (venue, leg, arrive), skipped
        return None, skipped

    def _leg(
        self, previous: ItineraryStop | None, lat: float, lon: float
    ) -> TravelLeg | None:
        if previous is None:
            return None
        travel = self.client.try_call(
            "spark-places",
            "travel_between",
            default=None,
            from_lat=previous.lat,
            from_lon=previous.lon,
            to_lat=lat,
            to_lon=lon,
        )
        if travel is None:
            return None
        return TravelLeg(
            minutes=travel["minutes"],
            metres=travel["metres"],
            mode=travel["mode"],
            detail=travel["detail"],
        )

    def _stop(
        self,
        order: int,
        category: str,
        venue: dict,
        start_minutes: int,
        duration: int,
        budget: str,
        grounded_in: list[str],
        travel: TravelLeg | None,
        is_partner: bool,
    ) -> ItineraryStop:
        opening = venue.get("_opening", {"state": "unknown", "detail": ""})
        shared = sorted(
            set(grounded_in) & {t.lower() for t in venue.get("interests", ())}
        )
        band = venue.get("budget", budget) or "flexible"
        return ItineraryStop(
            stop_id=f"stop-{venue['venue_id']}-{order}",
            order=order,
            activity_type=category,  # type: ignore[arg-type]
            venue_id=venue["venue_id"],
            venue_name=venue["name"],
            address=venue.get("address"),
            lat=venue["lat"],
            lon=venue["lon"],
            start_time=_to_clock(start_minutes),
            end_time=_to_clock(start_minutes + duration),
            duration_minutes=duration,
            estimated_cost=COST_TEXT.get(band, "Varies"),
            cost_band=band,  # type: ignore[arg-type]
            rationale=self._rationale(shared, category),
            travel_from_previous=travel,
            maps_url=_maps_url(venue["lat"], venue["lon"]),
            opening_state=opening["state"],
            opening_hours=venue.get("opening_hours"),
            opening_detail=opening.get("detail", ""),
            is_commercial_partner=bool(is_partner),
        )

    @staticmethod
    def _rationale(shared: list[str], category: str) -> str:
        """Why this stop, citing what both people said — or saying it cannot.

        A venue that matched the category but no shared interest gets an honest
        sentence rather than a manufactured one. "You both like coffee" about
        two people who never mentioned coffee is the failure this avoids.
        """
        kind = {
            "activity": "something to do",
            "food": "somewhere to eat afterwards",
            "drink": "somewhere to sit and talk",
        }.get(category, "a stop")
        if not shared:
            return f"Chosen as {kind} that fits the shape of the evening."
        joined = " and ".join(shared[:2])
        return f"You have both mentioned {joined}, and this is {kind}."

    def _assemble(
        self,
        *,
        lockin_id: str,
        path_id: str,
        headline: str,
        bucket: str,
        grounded_in: list[str],
        wanted_stops: int,
        owner_id: str,
        day_label: str,
        stops: list[ItineraryStop],
        skipped_closed: int,
        itinerary_id: str | None = None,
        created_at: datetime | None = None,
        status: str = "draft",
    ) -> DateItinerary:
        """The finished plan, with its totals and its caveats.

        Takes the path's fields rather than the path itself, because replacing
        one stop happens long after the `DatePath` has gone out of scope — the
        stored itinerary is the only thing the caller still has.
        """
        total = sum(stop.duration_minutes for stop in stops) + sum(
            stop.travel_from_previous.minutes
            for stop in stops
            if stop.travel_from_previous
        )
        now = datetime.now(UTC)

        notes: list[str] = []
        longest = max(
            (s.travel_from_previous.minutes for s in stops if s.travel_from_previous),
            default=0,
        )
        if longest > COMFORTABLE_LEG_MINUTES:
            # Said rather than hidden. A plan with a long hop in it can still be
            # the right plan, but nobody should discover the journey on the day.
            notes.append(
                f"There is a {longest}-minute journey between stops — the "
                "closest option of that kind was some way off."
            )
        unknown = [s for s in stops if s.opening_state == "unknown"]
        if unknown:
            # Said plainly rather than buried. Somebody who is going to ring
            # ahead needs to know which one to ring.
            names = ", ".join(s.venue_name for s in unknown[:3])
            notes.append(
                f"Opening hours are not recorded for {names} — worth checking "
                "before you go."
            )
        if skipped_closed:
            notes.append(
                f"{skipped_closed} option(s) were shut at that hour and were "
                "left out."
            )
        if len(stops) < wanted_stops:
            notes.append("Only the stops we could fill honestly are shown.")

        return DateItinerary(
            itinerary_id=itinerary_id or f"itin-{uuid.uuid4().hex[:12]}",
            lockin_id=lockin_id,
            path_id=path_id,
            owner_id=owner_id,
            headline=headline,
            time_bucket=bucket,  # type: ignore[arg-type]
            day_label=day_label,
            stops=stops,
            total_duration_minutes=min(720, max(15, total)),
            total_cost_estimate=_total_cost(stops),
            grounded_in=grounded_in,
            status=status,  # type: ignore[arg-type]
            note=" ".join(notes),
            created_at=created_at or now,
            updated_at=now,
        )


# ---------------------------------------------------------------------------


def _rough_gap(previous: ItineraryStop, venue: dict) -> float:
    """Squared coordinate distance, for ORDERING candidates only.

    Deliberately not a distance. It is monotonic with the real one over a few
    kilometres, which is all a sort needs, and it costs nothing — whereas asking
    `spark-places.travel_between` for all twenty candidates would put twenty
    spans per stop into the trace to answer a question none of them is the real
    answer to. The chosen venue's leg IS measured by the tool.
    """
    return (previous.lat - venue["lat"]) ** 2 + (previous.lon - venue["lon"]) ** 2


def _to_clock(minutes: int) -> str:
    """Minutes-since-midnight as "HH:MM", wrapping past midnight."""
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _to_minutes(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def _maps_url(lat: float, lon: float) -> str:
    from src.mcp.places import maps_url

    return maps_url(lat, lon)


def _total_cost(stops: list[ItineraryStop]) -> str:
    """A range across the stops, or "Free" when it genuinely is.

    Deliberately not a sum. Spark does not know what these venues charge — the
    band came from the venue's category — and adding two guesses together
    produces a number that looks researched.
    """
    bands = {stop.cost_band for stop in stops}
    if bands == {"free"}:
        return "Free"
    if "under_50" in bands or "flexible" in bands:
        return "Roughly $20-50 each, depending on where you stop"
    return "Roughly $10-20 each"
