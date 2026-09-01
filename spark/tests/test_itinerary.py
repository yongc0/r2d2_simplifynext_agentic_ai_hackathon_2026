"""The date planner: real venues, real times, and the things it refuses to do.

Two of these tests matter more than the rest and are named so they are hard to
delete quietly:

  `test_a_missing_venue_file_produces_no_venues_at_all` — the planner must fail
  visibly rather than invent an address. A fabricated venue is a real person
  standing outside a building that was never there.

  `test_a_closed_venue_is_never_a_stop` — a venue that is shut when you would
  arrive is dropped, not rendered with a warning. A venue with no recorded hours
  is marked unknown and never assumed open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.itinerary import ItineraryAgent, NoItinerary
from src.mcp import places
from src.mcp.registry import MCPClient
from src.schemas.agents import DatePath, DateStop
from src.schemas.itinerary import DateItinerary

FIXTURE = Path(__file__).parent / "fixtures" / "venues_test.json"


@pytest.fixture
def venues(monkeypatch):
    """Point `spark-places` at the synthetic fixture, and put it back after.

    The cache is cleared on the way in AND on the way out: a test that left the
    fixture cached would silently give every later test real-looking venues that
    do not exist.
    """
    monkeypatch.setattr(places, "DATA_PATH", FIXTURE)
    places.reload_venues()
    yield
    places.reload_venues()


@pytest.fixture
def agent():
    return ItineraryAgent(client=MCPClient(record_metrics=False))


def a_path(bucket: str = "evening", categories=("activity", "food")) -> DatePath:
    return DatePath(
        path_id="p-test",
        lockin_id="l-test",
        headline="A gallery, then somewhere to eat",
        stops=[
            DateStop(
                venue_id=f"abstract-{c}",
                activity=f"something {c}",
                category=c,
                is_commercial_partner=False,
            )
            for c in categories
        ],
        grounded_in=["photography", "cooking"],
        rationale="You have both mentioned photography.",
        fit_score=0.8,
        proposed_bucket=bucket,
    )


# ---------------------------------------------------------------------------
# What it refuses to do
# ---------------------------------------------------------------------------


def test_a_missing_venue_file_produces_no_venues_at_all(agent, monkeypatch):
    """No data means an explicit unavailable state, never an invented place."""
    monkeypatch.setattr(places, "DATA_PATH", Path("does-not-exist.json"))
    places.reload_venues()
    try:
        result = agent.build(a_path(), owner_id="u1")
    finally:
        places.reload_venues()

    assert isinstance(result, NoItinerary)
    assert result.data_unavailable is True
    assert "invent" in result.reason.lower() or "no venue data" in result.reason.lower()


def test_a_closed_venue_is_never_a_stop(venues, agent):
    """`test-a3-night-only` opens at 22:00. An evening plan starts at 18:00, so
    it must not appear — and something that IS open must be chosen instead."""
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    assert all(stop.venue_id != "test-a3-night-only" for stop in result.stops)
    assert all(stop.opening_state != "closed" for stop in result.stops)


def test_unknown_hours_are_said_out_loud_not_assumed_open(venues, agent):
    """`test-a2` has no `opening_hours`. If it is used, the plan must SAY the
    hours are unknown rather than presenting it as open."""
    result = agent.build(
        a_path(categories=("activity",)),
        owner_id="u1",
        exclude_venue_ids=frozenset({"test-a1"}),
    )
    assert isinstance(result, DateItinerary)
    unknown = [s for s in result.stops if s.opening_state == "unknown"]
    if unknown:
        assert "hours are not recorded" in result.note.lower()
        assert unknown[0].venue_name in result.note


def test_the_stop_model_will_not_hold_a_closed_venue(venues, agent):
    """Belt and braces: even if the planner had a bug, the schema refuses.

    The rule lives in `ItineraryStop`, so a closed venue cannot reach a screen
    through any code path — not just the one the planner happens to take.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="closed"):
        from src.schemas.itinerary import ItineraryStop

        ItineraryStop(
            stop_id="s", order=1, activity_type="food", venue_id="v",
            venue_name="Shut Place", lat=1.3, lon=103.8,
            start_time="19:00", end_time="20:00", duration_minutes=60,
            estimated_cost="Free", cost_band="free", rationale="r",
            maps_url="https://example.test", opening_state="closed",
        )


# ---------------------------------------------------------------------------
# What it produces
# ---------------------------------------------------------------------------


def test_a_plan_is_one_itinerary_not_a_pile_of_suggestions(venues, agent):
    """Ordered stops, contiguous times, and a walk between each pair."""
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    assert len(result.stops) >= 2

    assert [s.order for s in result.stops] == list(range(1, len(result.stops) + 1))
    assert result.stops[0].travel_from_previous is None
    for stop in result.stops[1:]:
        assert stop.travel_from_previous is not None
        assert stop.travel_from_previous.estimated is True

    # Each stop begins after the previous one ends, plus the walk.
    for earlier, later in zip(result.stops, result.stops[1:]):
        leg = later.travel_from_previous
        assert _minutes(later.start_time) == _minutes(earlier.end_time) + leg.minutes


def test_every_stop_carries_what_a_person_needs_to_go_there(venues, agent):
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    for stop in result.stops:
        assert stop.venue_name
        assert stop.start_time and stop.end_time
        assert stop.duration_minutes > 0
        assert stop.estimated_cost
        assert stop.rationale
        # A directions link that needs no API key and no credential.
        assert stop.maps_url.startswith("https://www.google.com/maps/dir/")
        assert f"{stop.lat},{stop.lon}" in stop.maps_url


def test_the_plan_credits_openstreetmap(venues, agent):
    """A licence condition, not a courtesy."""
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    assert "OpenStreetMap" in result.attribution


def test_planning_is_deterministic(venues, agent):
    """The same inputs give the same evening. A plan that reorders between takes
    cannot be filmed twice."""
    first = agent.build(a_path(), owner_id="u1")
    second = agent.build(a_path(), owner_id="u1")
    assert isinstance(first, DateItinerary)
    assert isinstance(second, DateItinerary)
    assert [s.venue_id for s in first.stops] == [s.venue_id for s in second.stops]
    assert [s.start_time for s in first.stops] == [s.start_time for s in second.stops]


def test_the_second_stop_is_near_the_first(venues, agent):
    """An itinerary, not a list of individually good venues.

    Ranked on fit alone the planner put a gallery in MacPherson and a coffee
    shop in Queenstown in the same evening — ten kilometres and a two-hour
    journey apart. Both stops were well chosen; the plan was nonsense.

    This is venue-to-venue distance between stops already selected for a plan.
    It is not proximity to a person, which is what invariant 3 forbids and which
    `spark-places` still cannot be asked for — see
    `test_places_is_never_given_a_person`.
    """
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    assert len(result.stops) >= 2

    chosen = result.stops[1]
    assert chosen.travel_from_previous is not None

    # Nothing eligible of that kind may be closer to stop 1 than the one picked.
    from src.mcp import places

    first = result.stops[0]
    for venue in places.search_places(
        interests=list(result.grounded_in), category=chosen.activity_type
    )["options"]:
        if venue["venue_id"] in {s.venue_id for s in result.stops}:
            continue
        gap = lambda v_lat, v_lon: (first.lat - v_lat) ** 2 + (first.lon - v_lon) ** 2
        assert gap(venue["lat"], venue["lon"]) >= gap(chosen.lat, chosen.lon), (
            f"{venue['name']} is closer to stop 1 than {chosen.venue_name} "
            "and was passed over"
        )


def test_a_long_journey_between_stops_is_said_out_loud(venues, agent):
    """A plan with a long hop can still be the right plan. Nobody should
    discover the journey on the day."""
    result = agent.build(a_path(), owner_id="u1")
    assert isinstance(result, DateItinerary)
    from src.agents.itinerary import COMFORTABLE_LEG_MINUTES

    longest = max(
        (s.travel_from_previous.minutes for s in result.stops if s.travel_from_previous),
        default=0,
    )
    if longest > COMFORTABLE_LEG_MINUTES:
        assert "journey between stops" in result.note


# ---------------------------------------------------------------------------
# Replacing one stop
# ---------------------------------------------------------------------------


def test_replacing_a_stop_keeps_the_others_and_re_times_what_follows(venues, agent):
    """The requirement's subtlety: earlier stops are untouched, later ones move.

    A different venue is a different walk. A planner that left the later times
    alone would hand somebody a schedule that no longer adds up.
    """
    original = agent.build(a_path(), owner_id="u1")
    assert isinstance(original, DateItinerary)
    assert len(original.stops) >= 2

    replaced = agent.replace_stop(original, order=2)
    if isinstance(replaced, NoItinerary):
        pytest.skip("the fixture has no alternative of that kind to swap in")

    # Stop 1 is byte-for-byte what it was.
    assert replaced.stops[0].venue_id == original.stops[0].venue_id
    assert replaced.stops[0].start_time == original.stops[0].start_time
    # Stop 2 is genuinely different.
    assert replaced.stops[1].venue_id != original.stops[1].venue_id
    # And the times still add up.
    leg = replaced.stops[1].travel_from_previous
    assert _minutes(replaced.stops[1].start_time) == (
        _minutes(replaced.stops[0].end_time) + leg.minutes
    )
    # Same plan, edited — not a second plan.
    assert replaced.itinerary_id == original.itinerary_id


def test_a_failed_replacement_does_not_destroy_the_plan(venues, agent):
    """Asking for something that does not exist must cost nothing."""
    original = agent.build(a_path(), owner_id="u1")
    assert isinstance(original, DateItinerary)
    result = agent.replace_stop(original, order=99)
    assert isinstance(result, NoItinerary)
    assert "99" in result.reason


def _minutes(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)
