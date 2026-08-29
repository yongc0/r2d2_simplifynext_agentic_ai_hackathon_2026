"""The Date Agent — three paths for a pair who have already met.

This is the half of the product that is not waiting. Spark finds one person a
day; once two people have exchanged names, the Date Agent is what turns "we
should meet sometime" — where most of these connections quietly die — into
three evenings a person can say yes or no to.

THE INVARIANT QUESTION THIS AGENT RAISES, AND HOW IT IS ANSWERED

Invariant 3 forbids rendering a place, and a date plan obviously points
somewhere. The two are reconciled by *when* and by *what*:

  WHEN — planning runs on a `LockIn`, which exists only after a mutual reveal.
  Two people choosing where to meet are picking a destination together. That is
  not a disclosure of where either of them was.

  WHAT — the venue search is never given a cell, a coordinate, a distance, or
  either person's overlap history. `test_venue_search_cannot_be_given_a_location`
  asserts that structurally, because a search that accepted a location would
  become "near where you both were" — the exact inference this product exists to
  prevent, arriving through the one feature allowed to name a place.
"""

from __future__ import annotations

import inspect
from datetime import date as Date
from datetime import datetime

import pytest

from src.agents.date import DateAgent
from src.mcp import services
from src.mcp.registry import MCPClient
from src.mcp.services import WORLD
from src.schemas.core import LockIn, TimeBucket, User
from src.sim.world import SimWorldBuilder

from tests.conftest import make_user

DAY_ZERO = Date(2026, 9, 1)


@pytest.fixture()
def world():
    """The seeded world, so the venue list is the real one."""
    SimWorldBuilder(seed=42, persona_count=40).build(day_zero=DAY_ZERO, days=16)
    yield WORLD


@pytest.fixture()
def agent() -> DateAgent:
    return DateAgent(client=MCPClient())


def pair_with(interests: list[str], buckets: list[TimeBucket]) -> tuple[User, User]:
    """Two people who genuinely share these interests and this free time."""
    a = make_user("u-a", 0, "Elowen Brackley", interests=interests, buckets=buckets)
    b = make_user("u-b", 1, "Torin Kilbride", interests=interests, buckets=buckets)
    WORLD.users[a.id] = a
    WORLD.users[b.id] = b
    WORLD.availability[a.id] = list(buckets)
    WORLD.availability[b.id] = list(buckets)
    return a, b


def lockin_for(a: User, b: User) -> LockIn:
    return LockIn(
        id="lock-test",
        pair_id="pair-test",
        user_a=a.id,
        user_b=b.id,
        opened_at=datetime(2026, 9, 3, 21, 0),
        last_contact=datetime(2026, 9, 3, 21, 0),
    )


# ---------------------------------------------------------------------------
# The plan itself
# ---------------------------------------------------------------------------


def test_offers_three_paths_when_there_is_enough_to_work_with(world, agent) -> None:
    a, b = pair_with(
        ["cooking", "film", "reading", "live music"], [TimeBucket.EVENING]
    )
    plan = agent.plan(lockin_for(a, b), a, b)

    assert len(plan.paths) == 3
    assert plan.note == ""


def test_the_three_paths_are_genuinely_different(world, agent) -> None:
    """Three variations on one evening is a list, not a choice.

    The point of offering three is that the pair pick the shape of the night,
    so the lead venues must differ — and no venue may appear twice across the
    whole plan.
    """
    a, b = pair_with(
        ["cooking", "film", "reading", "live music"], [TimeBucket.EVENING]
    )
    plan = agent.plan(lockin_for(a, b), a, b)

    leads = [path.stops[0].venue_id for path in plan.paths]
    assert len(set(leads)) == len(leads)

    everything = [stop.venue_id for path in plan.paths for stop in path.stops]
    assert len(set(everything)) == len(everything), "a venue was reused"


def test_a_path_is_a_plan_rather_than_a_single_venue(world, agent) -> None:
    a, b = pair_with(["cooking", "baking", "coffee"], [TimeBucket.EVENING])
    plan = agent.plan(lockin_for(a, b), a, b)

    assert plan.paths
    # At least one path pairs something to do with somewhere to eat or sit.
    assert any(
        {stop.category for stop in path.stops} & {"food", "drink"}
        and any(stop.category == "activity" for stop in path.stops)
        for path in plan.paths
    )


# ---------------------------------------------------------------------------
# Grounding — the same rule the Communication Agent follows
# ---------------------------------------------------------------------------


def test_every_path_cites_something_both_people_said(world, agent) -> None:
    """CLAUDE.md forbids inventing a shared interest. A date suggestion is the
    most tempting place to do it, because almost anything sounds plausible."""
    shared = ["cooking", "film", "reading"]
    a = make_user("u-a", 0, "Elowen", interests=shared + ["chess"],
                  buckets=[TimeBucket.EVENING])
    b = make_user("u-b", 1, "Torin", interests=shared + ["swimming"],
                  buckets=[TimeBucket.EVENING])
    WORLD.users.update({a.id: a, b.id: b})
    WORLD.availability.update({a.id: [TimeBucket.EVENING], b.id: [TimeBucket.EVENING]})

    plan = agent.plan(lockin_for(a, b), a, b)
    assert plan.paths

    both = set(a.profile.interests) & set(b.profile.interests)
    for path in plan.paths:
        assert path.grounded_in, "a path with nothing to cite is a guess"
        for interest in path.grounded_in:
            assert interest in both, f"{interest!r} is not something both listed"
        # And the interest one of them has alone never appears as grounds.
        assert "chess" not in path.grounded_in
        assert "swimming" not in path.grounded_in


def test_says_so_rather_than_guessing_when_there_is_no_common_ground(
    world, agent
) -> None:
    a = make_user("u-a", 0, "Elowen", interests=["chess"], buckets=[TimeBucket.EVENING])
    b = make_user("u-b", 1, "Torin", interests=["swimming"], buckets=[TimeBucket.EVENING])
    WORLD.users.update({a.id: a, b.id: b})

    plan = agent.plan(lockin_for(a, b), a, b)
    assert plan.paths == []
    assert "both mentioned" in plan.note or "nothing" in plan.note.lower()


# ---------------------------------------------------------------------------
# INVARIANT 3 — the feature allowed to point somewhere, and its limits
# ---------------------------------------------------------------------------


def test_venue_search_cannot_be_given_a_location(world) -> None:
    """Structural, not behavioural.

    If `suggest_venues` ever accepts a cell, a coordinate or a distance, then
    "places near where you both were" becomes one keyword argument away — and
    that is the de-anonymisation vector the whole product was designed to
    remove. The signature is the guard.
    """
    params = set(inspect.signature(services.suggest_venues).parameters)
    forbidden = {
        "cell", "cell_id", "location", "lat", "lng", "latitude", "longitude",
        "coords", "coordinates", "near", "distance", "radius", "overlap",
        "postcode", "address", "place",
    }
    assert not (params & forbidden), f"venue search accepts a location: {params & forbidden}"


def test_venue_records_have_nowhere_to_put_a_place(world) -> None:
    """The other half of the same argument: even if something wanted to rank on
    location, no venue knows one."""
    forbidden = {
        "lat", "lng", "latitude", "longitude", "address", "postcode",
        "cell", "cell_id", "location", "distance", "coordinates",
    }
    for venue in WORLD.venues.values():
        assert not (set(venue) & forbidden), f"{venue['id']} carries a location"


def test_no_path_renders_a_place_or_a_distance(world, agent) -> None:
    """Venues are KINDS of place — "a hawker centre, one dish each and swap" —
    never a named business at an address."""
    a, b = pair_with(
        ["cooking", "film", "reading", "live music", "coffee"],
        [TimeBucket.EVENING],
    )
    plan = agent.plan(lockin_for(a, b), a, b)
    assert plan.paths

    import re

    banned = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:m|km|metres?|miles?)\b"
        r"|\b(?:lat|lng|latitude|longitude)\b"
        r"|\bnear(?:by|\s+you)\b"
        r"|\b\d+\s*min(?:ute)?s?\s+away\b"
        r"|\bRaffles Place|Tanjong Pagar|Bugis|Jurong East|Tampines\b",
        re.I,
    )
    for path in plan.paths:
        text = DateAgent.render_path(path) + " " + path.headline
        assert not banned.search(text), f"path names a location: {text}"


# ---------------------------------------------------------------------------
# Commercial partners
# ---------------------------------------------------------------------------


def test_a_partner_venue_is_always_labelled(world, agent) -> None:
    """§13.6. `is_commercial_partner` is required on `DateStop`, so a partner
    cannot be constructed without it — and `render_path` says so beside the
    venue rather than in fine print."""
    a, b = pair_with(["cooking", "baking", "live music", "film"], [TimeBucket.EVENING])
    plan = agent.plan(lockin_for(a, b), a, b)

    for path in plan.paths:
        rendered = DateAgent.render_path(path)
        for stop in path.stops:
            if stop.is_commercial_partner:
                assert "Spark partner venue" in rendered


def test_ranking_never_sees_the_partner_flag(world) -> None:
    """A partner venue may only appear where it already ranks.

    Asserted by flipping every partner flag and checking the ORDER does not
    move: if the flag influenced ranking, it would.
    """
    before = services.suggest_venues(["cooking", "baking"], "evening", limit=5)
    order_before = [o["venue_id"] for o in before["options"]]

    for venue in WORLD.venues.values():
        venue["is_commercial_partner"] = not venue["is_commercial_partner"]
    try:
        after = services.suggest_venues(["cooking", "baking"], "evening", limit=5)
        assert [o["venue_id"] for o in after["options"]] == order_before
    finally:
        for venue in WORLD.venues.values():
            venue["is_commercial_partner"] = not venue["is_commercial_partner"]


# ---------------------------------------------------------------------------
# Consent, and honest emptiness
# ---------------------------------------------------------------------------


def test_respects_a_person_turning_date_suggestions_off(world, agent) -> None:
    a, b = pair_with(["cooking", "film", "reading"], [TimeBucket.EVENING])
    b.consent_scope.allow_date_suggestions = False

    plan = agent.plan(lockin_for(a, b), a, b)
    assert plan.paths == []
    assert "turned date suggestions off" in plan.note


def test_says_when_the_two_are_never_free_together(world, agent) -> None:
    a = make_user("u-a", 0, "Elowen", interests=["cooking"], buckets=[TimeBucket.MORNING])
    b = make_user("u-b", 1, "Torin", interests=["cooking"], buckets=[TimeBucket.NIGHT])
    WORLD.users.update({a.id: a, b.id: b})
    WORLD.availability.update({a.id: [TimeBucket.MORNING], b.id: [TimeBucket.NIGHT]})

    plan = agent.plan(lockin_for(a, b), a, b)
    assert plan.paths == []
    assert "same times" in plan.note


def test_a_pair_free_only_at_night_still_gets_something(world, agent) -> None:
    """A regression, and the reason venue hours are banded per venue.

    Every venue used to be open in every bucket EXCEPT night, so a pair whose
    only shared free time was late got nothing — while the one venue explicitly
    about being late, "late supper after everything else shuts", was closed then.
    """
    a, b = pair_with(["live music", "film", "cooking"], [TimeBucket.NIGHT])
    plan = agent.plan(lockin_for(a, b), a, b)

    assert plan.paths, "nothing offered to a pair who are only free at night"
    assert all(p.proposed_bucket is TimeBucket.NIGHT for p in plan.paths)


def test_tries_every_shared_bucket_not_only_the_first(world, agent) -> None:
    """Taking `buckets[0]` and giving up threw away the pair's other free times."""
    # Nothing in the world suits `early_morning` for these interests; the
    # evening does. The agent must find it rather than stop at the first.
    a, b = pair_with(
        ["board games", "chess"], [TimeBucket.EARLY_MORNING, TimeBucket.EVENING]
    )
    plan = agent.plan(lockin_for(a, b), a, b)

    assert plan.paths
    assert all(p.proposed_bucket is TimeBucket.EVENING for p in plan.paths)


# ---------------------------------------------------------------------------
# Determinism — a suggestion that changes between takes cannot be filmed twice
# ---------------------------------------------------------------------------


def test_the_same_pair_gets_the_same_plan_every_time(world, agent) -> None:
    a, b = pair_with(["cooking", "film", "reading"], [TimeBucket.EVENING])
    lockin = lockin_for(a, b)

    first = agent.plan(lockin, a, b)
    second = agent.plan(lockin, a, b)
    assert first.model_dump() == second.model_dump()
