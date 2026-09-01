"""The itinerary and reflection routes, and the privacy they are built around.

The reflection tests are the important ones. A post-date form that asks "would
you see them again" is only safe if the answer cannot travel, and "cannot" has
to mean there is no route that returns it — not that no screen currently shows
it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.session import get_session, reset_session
from src.mcp import places

FIXTURE = Path(__file__).parent / "fixtures" / "venues_test.json"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(places, "DATA_PATH", FIXTURE)
    places.reload_venues()
    reset_session(seed=42)
    yield TestClient(create_app())
    places.reload_venues()


@pytest.fixture
def stored_itinerary(client):
    """A saved plan, built straight through the store.

    The `/plans` hub needs a lock-in, which needs a completed encounter and a
    mutual reveal — a long way round for a test about reflections. This uses the
    same store the route does, so what is asserted is the real read path.
    """
    from datetime import UTC, datetime

    from src.schemas.itinerary import DateItinerary, ItineraryStop

    session = get_session()
    owner = session.viewer_user_id()
    now = datetime.now(UTC)
    itinerary = DateItinerary(
        itinerary_id="itin-test-1",
        lockin_id="lock-test-1",
        path_id="p-test",
        owner_id=owner,
        headline="A gallery, then somewhere to eat",
        time_bucket="evening",
        day_label="An evening",
        stops=[
            ItineraryStop(
                stop_id="s1", order=1, activity_type="activity",
                venue_id="test-a1", venue_name="Test Gallery One",
                address="1 Test Street 018956", lat=1.30, lon=103.80,
                start_time="18:00", end_time="19:15", duration_minutes=75,
                estimated_cost="Free", cost_band="free",
                rationale="You have both mentioned photography.",
                maps_url="https://www.google.com/maps/dir/?api=1"
                "&destination=1.3,103.8&travelmode=walking",
                opening_state="open", opening_hours="Mo-Su 10:00-19:00",
            )
        ],
        total_duration_minutes=75,
        total_cost_estimate="Free",
        grounded_in=["photography"],
        created_at=now,
        updated_at=now,
    )
    return session.itineraries.save(itinerary), owner


# ---------------------------------------------------------------------------
# The unavailable state
# ---------------------------------------------------------------------------


def test_places_status_reports_whether_real_data_is_loaded(client):
    body = client.get("/api/places/status").json()
    assert body["available"] is True
    assert body["count"] > 0
    assert "OpenStreetMap" in body["attribution"]


def test_places_status_says_so_when_there_is_no_data(client, monkeypatch):
    """The client must be able to tell "nothing matched" from "we have nothing",
    because they are different facts and only one is fixable by the user."""
    monkeypatch.setattr(places, "DATA_PATH", Path("nope.json"))
    places.reload_venues()
    body = client.get("/api/places/status").json()
    assert body["available"] is False
    assert body["count"] == 0
    assert "fetch_venues" in body["note"]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_lists_this_viewers_plans(client, stored_itinerary):
    _itinerary, _owner = stored_itinerary
    rows = client.get("/api/itineraries").json()
    assert [r["itineraryId"] for r in rows] == ["itin-test-1"]
    assert rows[0]["status"] == "draft"
    assert rows[0]["stops"][0]["venueName"] == "Test Gallery One"


def test_history_never_leaks_another_persons_plan(client, stored_itinerary):
    """A plan belonging to somebody else 404s rather than 403s: a 403 confirms
    that a plan exists under that id, which is a fact about their evening."""
    from src.api.session import get_session

    session = get_session()
    itinerary, owner = stored_itinerary
    other = itinerary.model_copy(
        update={"itinerary_id": "itin-someone-else", "owner_id": f"not-{owner}"}
    )
    session.itineraries.save(other)

    assert client.get("/api/itineraries/itin-someone-else").status_code == 404
    rows = client.get("/api/itineraries").json()
    assert all(r["itineraryId"] != "itin-someone-else" for r in rows)


def test_a_person_can_move_a_plan_along(client, stored_itinerary):
    for status in ("proposed", "confirmed", "cancelled"):
        body = client.put(
            "/api/itineraries/itin-test-1/status", json={"status": status}
        ).json()
        assert body["status"] == status


def test_a_person_cannot_mark_a_future_date_completed(client, stored_itinerary):
    """`completed` is the clock's, and the reflection form is what records that
    an evening actually happened."""
    response = client.put(
        "/api/itineraries/itin-test-1/status", json={"status": "completed"}
    )
    assert response.status_code == 422
    assert "set by Spark" in response.json()["detail"]


def test_there_is_no_status_meaning_they_turned_you_down(client):
    """Invariant 2, still holding after the reveal. A plan the other person did
    not take up is `cancelled` — the same as one nobody got round to."""
    from src.schemas.itinerary import ItineraryStatus
    from typing import get_args

    statuses = set(get_args(ItineraryStatus))
    for word in ("rejected", "declined", "refused", "ghosted", "ignored"):
        assert not any(word in s for s in statuses), (
            f"a status containing {word!r} would let the interface tell somebody "
            "they were turned down"
        )


# ---------------------------------------------------------------------------
# Reflections — private, and structurally so
# ---------------------------------------------------------------------------


def test_a_reflection_comes_back_only_to_its_author(client, stored_itinerary):
    written = client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={
            "overall": 5,
            "ratings": {"conversation": 5, "location": 4},
            "secondDate": "yes",
            "notes": "Lovely evening.",
        },
    )
    assert written.status_code == 200
    body = written.json()
    assert body["overall"] == 5
    assert body["secondDate"] == "yes"
    assert "Only you can see this" in body["privacyNote"]

    read_back = client.get("/api/itineraries/itin-test-1/reflection").json()
    assert read_back["reflectionId"] == body["reflectionId"]


def test_no_route_anywhere_returns_someone_elses_reflection(client, stored_itinerary):
    """The structural half of the promise.

    Not "no screen shows it" — no route can produce it. Every read path in the
    store takes an owner and filters on it, and this asserts the API has no way
    round that.
    """
    from src.api.session import get_session

    session = get_session()
    itinerary, owner = stored_itinerary
    session.itineraries.record_reflection(
        itinerary_id="itin-test-1",
        lockin_id="lock-test-1",
        owner_id=f"not-{owner}",
        overall=1,
        ratings={},
        second_date="no",
        notes="private to them",
    )
    # This viewer wrote nothing, so there is nothing for them to read — the
    # other person's row is invisible rather than merely unrendered.
    assert client.get("/api/itineraries/itin-test-1/reflection").status_code == 404

    payload = client.get("/api/itineraries").text
    assert "private to them" not in payload


def test_the_itinerary_never_says_whether_they_reflected(client, stored_itinerary):
    """`hasReflection` is the viewer's own.

    A field saying the other person had filled the form in would let somebody
    infer an answer they were never meant to see — including a "no".
    """
    before = client.get("/api/itineraries/itin-test-1").json()
    assert before["hasReflection"] is False

    client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={"overall": 4, "secondDate": "maybe"},
    )
    after = client.get("/api/itineraries/itin-test-1").json()
    assert after["hasReflection"] is True
    # And there is no second field about anybody else.
    assert not [k for k in after if "their" in k.lower() or "peer" in k.lower()]


def test_saying_no_looks_exactly_like_saying_yes(client, stored_itinerary):
    """The whole reason a reflection can be honest.

    Two people answer the same form in opposite directions. Everything the OTHER
    party could observe — the stored plan, its status, the history listing — must
    be identical either way.
    """
    def observable_after(answer: str) -> tuple:
        reset_session(seed=42)
        fresh = TestClient(create_app())
        session = get_session()
        itinerary, _owner = stored_itinerary
        session.itineraries.save(
            itinerary.model_copy(update={"owner_id": session.viewer_user_id()})
        )
        fresh.post(
            "/api/itineraries/itin-test-1/reflection",
            json={"overall": 4, "secondDate": answer},
        )
        plan = fresh.get("/api/itineraries/itin-test-1").json()
        return (plan["status"], plan["note"], plan["headline"], len(plan["stops"]))

    assert observable_after("yes") == observable_after("no")


def test_a_reflection_can_be_deleted(client, stored_itinerary):
    written = client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={"overall": 2, "secondDate": "no"},
    ).json()
    assert client.delete(f"/api/reflections/{written['reflectionId']}").status_code == 200
    assert client.get("/api/itineraries/itin-test-1/reflection").status_code == 404


def test_reflecting_twice_leaves_one_live_answer(client, stored_itinerary):
    """Changing your mind must not double-count in the recommender."""
    client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={"overall": 2, "secondDate": "no"},
    )
    second = client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={"overall": 5, "secondDate": "yes"},
    ).json()
    assert client.get("/api/itineraries/itin-test-1/reflection").json()[
        "reflectionId"
    ] == second["reflectionId"]


def test_a_reflection_marks_the_date_as_having_happened(client, stored_itinerary):
    client.post(
        "/api/itineraries/itin-test-1/reflection",
        json={"overall": 4, "secondDate": "maybe"},
    )
    assert client.get("/api/itineraries/itin-test-1").json()["status"] == "completed"
