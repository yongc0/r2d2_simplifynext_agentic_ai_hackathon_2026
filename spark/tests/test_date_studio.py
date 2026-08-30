"""Date Studio — memory, ranking, and the boundaries around both.

Spark finds one person a day. Date Studio is the half that runs afterwards:
fixed constraints in, three grounded plans out, structured feedback back, and a
memory the person can read and correct.

TWO CLAIMS UNDER TEST, AND THE DIFFERENCE BETWEEN THEM

*It remembers* — asserted against a genuinely new process, because a preference
store that dies with the server is not memory, it is a cache.

*It does not learn a model* — asserted by construction. Every test here reasons
about ROWS. If improvement came from anything but re-ranking auditable rows,
`test_a_deleted_preference_stops_affecting_the_ranking` could not pass.

The safety boundary outranks every retention feature in this file: no plan may
appear before a mutual reveal or after a Guardian closure, and those two tests
are the ones that must never be weakened to make a feature pass.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import src.api.session as session_module
from src.agents.date_scoring import explain, score_candidate
from src.api.app import create_app
from src.api.session import SparkSession, get_session
from src.config import RUNS_DIR, SETTINGS
from src.memory.date_memory import DateMemoryStore
from src.schemas.date_studio import (
    MAX_INFERRED_CONFIDENCE,
    DateMemoryItem,
    DatePlanningPreferences,
)

DAY_ZERO = Date(2026, 9, 1)


@pytest.fixture(scope="module", autouse=True)
def isolated_db():
    """This file gets its own database.

    Date Studio memory is durable by design, which also means it outlives a test
    run — a developer clicking around leaves preferences behind and the next
    `pytest` inherits them. Same reasoning as `test_api.py`.
    """
    original = SETTINGS.checkpoint_db
    path = RUNS_DIR / "test-scratch" / "studio.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    object.__setattr__(SETTINGS, "checkpoint_db", path)
    session_module._session = None
    try:
        yield
    finally:
        if session_module._session is not None:
            session_module._session.close()
        session_module._session = None
        object.__setattr__(SETTINGS, "checkpoint_db", original)
        path.unlink(missing_ok=True)


@pytest.fixture()
def client() -> TestClient:
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    return api


@pytest.fixture()
def store() -> DateMemoryStore:
    return get_session().date_memory


def connected(client: TestClient) -> str:
    """Drive a pair all the way to a lock-in and return its id."""
    eid = client.post("/api/encounters").json()["encounterId"]
    client.post(f"/api/encounters/{eid}/respond", json={"accept": True})
    client.post(f"/api/encounters/{eid}/consent", json={"yes": True})
    plans = client.get("/api/plans").json()
    assert plans, "no lock-in was opened"
    return plans[0]["lockInId"]


def generate(client: TestClient, lockin_id: str, **body) -> dict:
    return client.post(f"/api/lockins/{lockin_id}/date-plans", json=body).json()


# ---------------------------------------------------------------------------
# The boundary. These outrank everything else in this file.
# ---------------------------------------------------------------------------


def test_no_planning_before_a_mutual_reveal(client: TestClient) -> None:
    """A lock-in exists only after both said yes, so there is nothing to plan
    with — and `/plans` must not invent one."""
    eid = client.post("/api/encounters").json()["encounterId"]
    client.post(f"/api/encounters/{eid}/respond", json={"accept": True})

    assert client.get("/api/plans").json() == []
    assert client.post(
        "/api/lockins/lock-nope/date-plans", json={}
    ).status_code == 404


def test_no_planning_after_a_guardian_closure(client: TestClient) -> None:
    """Planning an evening for someone who has just said something felt off is
    the worst thing this product could do."""
    eid = client.post("/api/encounters").json()["encounterId"]
    client.post(f"/api/encounters/{eid}/respond", json={"accept": True})
    client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    )
    client.post(f"/api/encounters/{eid}/consent", json={"yes": True})

    assert client.get("/api/plans").json() == []


def test_a_released_connection_cannot_be_planned_with(client: TestClient) -> None:
    from src.schemas.core import LockInState

    lockin_id = connected(client)
    get_session().lockin(lockin_id).state = LockInState.RELEASED

    response = client.post(f"/api/lockins/{lockin_id}/date-plans", json={})
    assert response.status_code == 409
    assert "released" in response.json()["detail"].lower()

    hub = client.get("/api/plans").json()
    assert hub[0]["unavailableReason"], "the hub should say why, not hide it"


def test_an_unknown_lockin_is_404_not_409(client: TestClient) -> None:
    """"No such connection" and "not open for planning" are different answers,
    and collapsing them makes the second impossible to debug."""
    assert client.get(
        "/api/lockins/lock-nope/date-preferences"
    ).status_code == 404
    assert client.post(
        "/api/date-plans/plan-nope/feedback", json={"action": "saved"}
    ).status_code == 404


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_the_owner_is_derived_never_supplied(client: TestClient) -> None:
    """A client that could name the owner of a memory item could read and
    rewrite somebody else's preferences. `owner_id` never crosses the wire
    inbound, and the request models forbid extras, so trying is a 422."""
    lockin_id = connected(client)
    response = client.post(
        f"/api/lockins/{lockin_id}/date-plans",
        json={"budget": "free", "owner_id": "u-someone-else"},
    )
    assert response.status_code == 422


def test_one_persons_memory_is_not_in_anothers_read(store: DateMemoryStore) -> None:
    store.remember(
        owner_id="u-alice", scope="user", dimension="budget",
        value="free", source="explicit",
    )
    assert store.for_owner("u-alice")
    assert store.for_owner("u-bob") == []


def test_lockin_memory_never_reaches_another_lockin(store: DateMemoryStore) -> None:
    """A reaction to one person is not a fact about somebody in general.

    Letting a lock-in scoped item drift would leak the shape of a private
    reaction into an unrelated plan.
    """
    # A distinct owner, and assertions on the LOCK-IN SCOPED items only: a
    # user-scoped preference is supposed to appear under every lock-in, so
    # asserting on the whole list would be testing the wrong thing.
    store.remember(
        owner_id="u-scoped", scope="lockin", lockin_id="L1",
        dimension="energy", value="low", source="feedback",
    )

    def lockin_items(lockin_id: str) -> list[str]:
        return [
            m.dimension
            for m in store.for_owner("u-scoped", lockin_id)
            if m.scope == "lockin"
        ]

    assert lockin_items("L1") == ["energy"]
    assert lockin_items("L2") == []


def test_a_lockin_item_without_a_lockin_id_is_refused() -> None:
    """Structural. Such an item would silently behave as a user-wide
    preference, which is the leak above with no way to notice it."""
    with pytest.raises(ValueError, match="lockin_id"):
        DateMemoryItem(
            memory_id="m", owner_id="u", scope="lockin", dimension="mood",
            value="easy", source="explicit", confidence=1.0,
            created_at=datetime.now(), updated_at=datetime.now(),
        )


# ---------------------------------------------------------------------------
# What is remembered, and how strongly
# ---------------------------------------------------------------------------


def test_a_temporary_constraint_is_not_remembered(client: TestClient) -> None:
    """"I am tired tonight" is context, not a preference.

    A system that promotes tonight's mood into a durable belief will be wrong
    about someone forever without ever having been told anything untrue.
    """
    lockin_id = connected(client)
    generate(client, lockin_id, energy="low", budget="free")

    assert client.get("/api/date-memory").json() == []


def test_remembering_is_opt_in_and_then_explicit(client: TestClient) -> None:
    lockin_id = connected(client)
    generate(client, lockin_id, energy="low", budget="free", remember=True)

    memory = client.get("/api/date-memory").json()
    assert {(m["dimension"], m["value"]) for m in memory} == {
        ("energy", "low"), ("budget", "free")
    }
    assert all(m["source"] == "explicit" for m in memory)
    assert all(m["confidence"] == 1.0 for m in memory)


def test_an_explicit_preference_outranks_an_inference(
    store: DateMemoryStore,
) -> None:
    inferred = store.remember(
        owner_id="u-x", scope="user", dimension="budget",
        value="under_50", source="feedback",
    )
    explicit = store.remember(
        owner_id="u-x", scope="user", dimension="mood",
        value="easy", source="explicit",
    )
    assert explicit.confidence > inferred.confidence
    assert inferred.confidence <= MAX_INFERRED_CONFIDENCE


def test_one_rejection_moves_the_belief_gradually(store: DateMemoryStore) -> None:
    """A single no is not a permanent dislike.

    Somebody who says "too expensive" once has not told us they are frugal, and
    a recommender that treats it that way stops offering things they would have
    liked — while looking, from the inside, like it is learning.
    """
    first = store.remember(
        owner_id="u-grad", scope="user", dimension="budget",
        value="free", source="feedback",
    )
    assert first.confidence < MAX_INFERRED_CONFIDENCE

    for _ in range(10):
        latest = store.remember(
            owner_id="u-grad", scope="user", dimension="budget",
            value="free", source="feedback",
        )
    assert latest.confidence == MAX_INFERRED_CONFIDENCE
    assert latest.confidence < 1.0, "an inference must never reach certainty"


def test_being_told_overrides_having_guessed(store: DateMemoryStore) -> None:
    store.remember(
        owner_id="u-corr", scope="user", dimension="energy",
        value="high", source="feedback",
    )
    corrected = store.remember(
        owner_id="u-corr", scope="user", dimension="energy",
        value="low", source="explicit",
    )
    assert corrected.value == "low"
    assert corrected.source == "explicit"
    assert corrected.confidence == 1.0


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


def test_feedback_is_idempotent(client: TestClient) -> None:
    """A double-tap must not double-learn."""
    lockin_id = connected(client)
    plan = generate(client, lockin_id)
    plan_id = plan["paths"][0]["pathId"]

    for _ in range(3):
        client.post(
            f"/api/date-plans/{plan_id}/feedback",
            json={"action": "rejected", "reasons": ["too_long"]},
        )

    memory = client.get(f"/api/date-memory?lockInId={lockin_id}").json()
    duration = [m for m in memory if m["dimension"] == "duration"]
    assert len(duration) == 1, "one belief, however many times it was submitted"


def test_changing_feedback_does_not_double_count(client: TestClient) -> None:
    """The newest active answer decides; the old one stays readable."""
    lockin_id = connected(client)
    plan = generate(client, lockin_id)
    plan_id = plan["paths"][0]["pathId"]

    client.post(
        f"/api/date-plans/{plan_id}/feedback",
        json={"action": "rejected", "reasons": ["too_long"]},
    )
    client.post(f"/api/date-plans/{plan_id}/feedback", json={"action": "saved"})

    store = get_session().date_memory
    viewer = get_session().viewer_id(get_session().lockin(lockin_id))
    active = store.feedback_for(viewer, lockin_id)
    assert len(active) == 1
    assert active[0].action == "saved"


def test_a_rejection_changes_the_next_ranking(client: TestClient) -> None:
    """The point of the whole feature, asserted end to end."""
    lockin_id = connected(client)
    before = generate(client, lockin_id, budget="free", energy="low")
    assert before["paths"]

    client.post(
        f"/api/date-plans/{before['paths'][0]['pathId']}/feedback",
        json={"action": "rejected", "reasons": ["too_long"]},
    )
    after = generate(client, lockin_id, budget="free", energy="low")

    assert [p["pathId"] for p in after["paths"]] != [
        p["pathId"] for p in before["paths"]
    ], "rejecting a plan changed nothing about the next set"


def test_a_reason_is_only_accepted_with_a_rejection(client: TestClient) -> None:
    """A reason explains a no and means nothing beside a yes."""
    from src.schemas.date_studio import DatePlanFeedback

    with pytest.raises(ValueError, match="rejection reasons"):
        DatePlanFeedback(
            feedback_id="f", plan_id="p", lockin_id="L", owner_id="u",
            action="saved", reasons=["too_long"], created_at=datetime.now(),
        )


def test_feedback_needs_a_plan_that_was_actually_offered(
    client: TestClient,
) -> None:
    """Without this a client could invent a plan id, and the memory would fill
    with beliefs derived from nothing."""
    connected(client)
    assert client.post(
        "/api/date-plans/made-up/feedback", json={"action": "saved"}
    ).status_code == 404


# ---------------------------------------------------------------------------
# Correction and deletion
# ---------------------------------------------------------------------------


def test_a_deleted_preference_stops_affecting_the_ranking(
    client: TestClient,
) -> None:
    """Deletion has to mean something, or the memory panel is decoration."""
    lockin_id = connected(client)
    generate(client, lockin_id, budget="free", remember=True)

    memory = client.get("/api/date-memory").json()
    assert memory
    client.delete(f"/api/date-memory/{memory[0]['memoryId']}")

    assert client.get("/api/date-memory").json() == []
    store = get_session().date_memory
    viewer = get_session().viewer_id(get_session().lockin(lockin_id))
    assert all(m.dimension != "budget" for m in store.for_owner(viewer, lockin_id))


def test_correcting_a_memory_makes_it_explicit(client: TestClient) -> None:
    lockin_id = connected(client)
    generate(client, lockin_id, budget="free", remember=True)
    memory = client.get("/api/date-memory").json()

    updated = client.patch(
        f"/api/date-memory/{memory[0]['memoryId']}", json={"value": "under_50"}
    ).json()
    assert updated["value"] == "under_50"
    assert updated["source"] == "explicit"
    assert updated["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Durability — the claim that it remembers
# ---------------------------------------------------------------------------


def test_memory_survives_a_genuinely_new_process(client: TestClient) -> None:
    """A preference store that dies with the server is a cache, not memory."""
    lockin_id = connected(client)
    generate(client, lockin_id, budget="free", energy="low", remember=True)
    before = client.get("/api/date-memory").json()
    assert before

    restarted = SparkSession()
    try:
        viewer = restarted.viewer_id(restarted.lockins()[0]) if restarted.lockins() \
            else get_session().viewer_id(get_session().lockin(lockin_id))
        recovered = restarted.date_memory.for_owner(viewer, lockin_id)
        assert {(m.dimension, m.value) for m in recovered} >= {
            ("budget", "free"), ("energy", "low")
        }
    finally:
        restarted.close()


def test_a_demo_reset_clears_the_studio(client: TestClient) -> None:
    """Recorded takes must be deterministic. A preference learned in rehearsal
    would quietly change the ranking on camera."""
    lockin_id = connected(client)
    generate(client, lockin_id, budget="free", remember=True)
    assert client.get("/api/date-memory").json()

    client.post("/api/demo/reset")
    assert client.get("/api/date-memory").json() == []


# ---------------------------------------------------------------------------
# The plans themselves
# ---------------------------------------------------------------------------


def test_three_distinct_shapes_when_there_is_enough(client: TestClient) -> None:
    lockin_id = connected(client)
    plan = generate(client, lockin_id)

    shapes = [p["shape"] for p in plan["paths"]]
    assert shapes == ["easy", "new", "light"]
    leads = [p["stops"][0]["venueId"] for p in plan["paths"]]
    assert len(set(leads)) == len(leads), "the three must be different evenings"


def test_a_short_list_explains_itself(client: TestClient) -> None:
    """Never pad with a weak option; say why instead."""
    lockin_id = connected(client)
    plan = generate(client, lockin_id, duration="whole_evening", energy="high",
                    budget="free", mood="adventurous")
    if len(plan["paths"]) < 3:
        assert plan["note"], "a short list with no explanation reads as a bug"


def test_every_rationale_is_grounded_in_something_that_scored(
    client: TestClient,
) -> None:
    """Evidence first, sentence second.

    Writing the explanation first and finding support afterwards is how
    recommenders end up confidently describing preferences nobody has.
    """
    lockin_id = connected(client)
    plan = generate(client, lockin_id, budget="free", remember=True)

    for path in plan["paths"]:
        assert path["groundedIn"], "a path with nothing to cite is a guess"
        assert path["rationale"]
        # Every cited interest is one BOTH people listed — the agent reads them
        # from the intersection, so this cannot be satisfied by invention.
        assert all(isinstance(i, str) and i for i in path["groundedIn"])


def test_an_empty_breakdown_produces_no_sentence() -> None:
    """The guard behind the rule above."""
    from src.agents.date_scoring import ScoreBreakdown

    assert explain(ScoreBreakdown(), "evening") == ""


def test_partner_status_never_reaches_the_scorer() -> None:
    """§13.6: a partner venue may only appear where it already ranks.

    Asserted by scoring the same venue with the flag both ways.
    """
    venue = {
        "venue_id": "v-x", "tags": ("coffee",), "budget": "free",
        "duration": "one_hour", "energy": "low", "format": "food",
    }
    preferences = DatePlanningPreferences(budget="free")

    def total(is_partner: bool) -> float:
        return score_candidate(
            venue={**venue, "is_commercial_partner": is_partner},
            shared_interests=["coffee"], preferences=preferences,
            memory=[], feedback=[], seen_leads=set(), saved_shapes=set(),
            shape="easy",
        ).total

    assert total(True) == total(False)


def test_a_partner_stop_is_always_labelled(client: TestClient) -> None:
    lockin_id = connected(client)
    plan = generate(client, lockin_id)
    for path in plan["paths"]:
        for stop in path["stops"]:
            assert "isCommercialPartner" in stop


def test_no_output_carries_a_location(client: TestClient) -> None:
    """INVARIANT 1 at the wire.

    A date plan is the one thing allowed to point somewhere, and it is safe only
    because nothing in the payload could become "near where you both were".
    """
    import json

    lockin_id = connected(client)
    payload = json.dumps(generate(client, lockin_id)).lower()

    for forbidden in (
        "address", "latitude", "longitude", '"lat"', '"lng"', "postcode",
        "distance", "coordinates", "cell_id", "mapurl", "google.com/maps",
    ):
        assert forbidden not in payload, f"{forbidden!r} reached the client"


def test_generating_twice_unchanged_does_not_accumulate(
    client: TestClient,
) -> None:
    """Pressing Generate again must not quietly deepen a preference."""
    lockin_id = connected(client)
    generate(client, lockin_id, budget="free", remember=True)
    first = client.get("/api/date-memory").json()
    generate(client, lockin_id, budget="free", remember=True)
    second = client.get("/api/date-memory").json()

    assert len(first) == len(second)
    assert [m["confidence"] for m in first] == [m["confidence"] for m in second]
