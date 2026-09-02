"""The HTTP boundary — the consent gates, reached the way a client reaches them.

WHY THIS FILE EXISTS

An audit found a real vulnerability here, and it was invisible to every other
test in the suite. `Command(resume=...)` is delivered to whichever interrupt is
currently pending, and neither `accept()` nor `consent()` checked which one that
was. So:

    POST /respond  {"accept": true}     -> answers the ACCEPT gate
    POST /respond  {"accept": true}     -> answers the REVEAL gate, with two
                                           yes votes nobody cast
    POST /consent  {"yes": false}       -> 200 mutual, with the other person's
                                           name

A user's explicit "no" arrived after the identities had already been exchanged.
That is invariant 1 failing — "no identity before both parties say yes" — via
the HTTP layer rather than via the graph, which is exactly why `test_graph.py`
and `test_consent.py` both passed throughout.

The lesson generalises: the graph's guarantees are only guarantees if the thing
driving the graph cannot drive it out of order. These tests exercise the
ordering, not the outcomes — `test_consent.py` already owns the outcomes.

`tests/conftest.py` forces the deterministic provider, so nothing here makes a
model call.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.api.session as session_module
from src.api.app import create_app
from src.config import RUNS_DIR, SETTINGS
from src.api.session import (
    EncounterClosed,
    EncounterNotFound,
    GateNotPending,
    SparkSession,
    get_session,
)
from src.safety.consent import reveal_permitted
from src.schemas.core import ConsentStage


@pytest.fixture(scope="module", autouse=True)
def isolated_checkpoints():
    """Give this file its own checkpoint database.

    The session state that makes restart recovery work — `run_id` and
    `current_eid` — is DURABLE, which is the whole point of it. That also means
    it outlives a test run: a developer poking at the API by hand leaves a
    `current_eid` behind, and the next `pytest` picks it up and opens that
    encounter instead of a fresh one. It cost a confusing failure here before
    this fixture existed.

    So the suite gets its own file. `SETTINGS` is a frozen dataclass, hence
    `object.__setattr__`; and the module-level session singleton is dropped so
    it rebuilds against the new path rather than holding a connection to the
    old one.
    """
    original = SETTINGS.checkpoint_db
    path = RUNS_DIR / "test-scratch" / "api-checkpoints.sqlite"
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
    """A client on a freshly reset session, so takes cannot bleed into one
    another through the durable checkpoint."""
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    return api


def open_encounter(client: TestClient) -> str:
    response = client.post("/api/encounters")
    assert response.status_code == 200, response.text
    return response.json()["encounterId"]


def respond(client: TestClient, eid: str, accept: bool):
    return client.post(f"/api/encounters/{eid}/respond", json={"accept": accept})


def consent(client: TestClient, eid: str, yes: bool):
    return client.post(f"/api/encounters/{eid}/consent", json={"yes": yes})


# ---------------------------------------------------------------------------
# The exploit, as it was reported
# ---------------------------------------------------------------------------


def test_the_reported_exploit_is_closed(client: TestClient) -> None:
    """The exact sequence from the audit, asserted step by step.

    The second `/respond` must be refused, and the later explicit "no" must not
    produce a person. Both halves matter: refusing the duplicate is the fix,
    and the absent identity is the property the fix exists to protect.
    """
    eid = open_encounter(client)

    assert respond(client, eid, True).status_code == 200

    duplicate = respond(client, eid, True)
    assert duplicate.status_code == 409
    # Actionable, per CLAUDE.md: it says which gate is pending and what to call.
    assert "reveal" in duplicate.json()["detail"]

    final = consent(client, eid, False)
    assert final.status_code == 200
    body = final.json()
    assert body["person"] is None
    assert body["outcome"] != "mutual"


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_happy_path_still_reveals(client: TestClient) -> None:
    """The fix must not close the gate on the ordinary case."""
    eid = open_encounter(client)
    assert respond(client, eid, True).status_code == 200

    body = consent(client, eid, True).json()
    assert body["outcome"] == "mutual"
    assert body["person"]["displayName"]


def test_consent_before_respond_is_refused(client: TestClient) -> None:
    eid = open_encounter(client)
    response = consent(client, eid, True)
    assert response.status_code == 409
    assert "accept" in response.json()["detail"]


def test_duplicate_consent_is_refused(client: TestClient) -> None:
    eid = open_encounter(client)
    respond(client, eid, True)
    assert consent(client, eid, True).status_code == 200

    second = consent(client, eid, True)
    assert second.status_code == 409
    assert second.json()["person" if "person" in second.json() else "detail"]


def test_respond_after_the_reveal_gate_opens_is_refused(client: TestClient) -> None:
    eid = open_encounter(client)
    respond(client, eid, True)
    assert respond(client, eid, False).status_code == 409


def test_a_finished_encounter_cannot_be_resumed(client: TestClient) -> None:
    """Once the encounter is over, both gates are closed to everyone."""
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)

    assert respond(client, eid, True).status_code == 409
    assert consent(client, eid, True).status_code == 409


def test_a_declined_encounter_cannot_be_reopened(client: TestClient) -> None:
    """A decline ends it. There is no second ask, which is the point —
    "are you sure?" is how a no becomes a yes."""
    eid = open_encounter(client)
    assert respond(client, eid, False).status_code == 200

    assert respond(client, eid, True).status_code == 409
    assert consent(client, eid, True).status_code == 409


@pytest.mark.parametrize(
    "prefix",
    [
        pytest.param([("consent", True)], id="consent-first"),
        pytest.param([("respond", True), ("respond", True)], id="double-respond"),
        pytest.param([("respond", True), ("consent", True), ("respond", True)],
                     id="respond-after-reveal"),
    ],
)
def test_an_explicit_no_never_reveals_after_any_bad_sequence(
    client: TestClient, prefix: list[tuple[str, bool]]
) -> None:
    """The property, stated directly.

    Whatever malformed sequence precedes it, a "no" at the reveal gate must
    never come back with a person. Parameterised over the sequences that were
    or could be exploits, so a future refactor that reopens one of them fails
    here rather than in production.
    """
    eid = open_encounter(client)
    for call, value in prefix:
        (respond if call == "respond" else consent)(client, eid, value)

    final = consent(client, eid, False)
    # Either the gate refuses it outright, or it answers honestly. What it may
    # never do is hand over an identity.
    if final.status_code == 200:
        assert final.json()["person"] is None
        assert final.json()["outcome"] != "mutual"
    else:
        assert final.status_code == 409


# ---------------------------------------------------------------------------
# Unknown and stale encounters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/encounters/enc-does-not-exist/respond", {"accept": True}),
        ("/api/encounters/enc-does-not-exist/consent", {"yes": True}),
    ],
)
def test_unknown_encounter_is_404_not_500(
    client: TestClient, path: str, body: dict
) -> None:
    """A made-up id is a client error with a useful message, not a traceback."""
    response = client.post(path, json=body)
    assert response.status_code == 404
    assert "enc-does-not-exist" in response.json()["detail"]


def test_unknown_encounter_card_is_404(client: TestClient) -> None:
    assert client.get("/api/encounters/enc-does-not-exist").status_code == 404


def test_ids_from_a_previous_take_are_not_resumable(client: TestClient) -> None:
    """A demo reset starts a new run, and old ids stop working.

    Deliberate: encounter ids are deterministic, so without the per-run thread
    id a retake would resume the PREVIOUS take's completed checkpoint and show
    its outcome. Better to refuse the stale id than to replay a stranger.
    """
    eid = open_encounter(client)
    respond(client, eid, True)

    client.post("/api/demo/reset")
    assert consent(client, eid, True).status_code == 404


# ---------------------------------------------------------------------------
# One encounter per person per day
# ---------------------------------------------------------------------------


def test_opening_twice_returns_the_same_encounter(client: TestClient) -> None:
    """One encounter per person per day is the product, not an optimisation.

    It also protects the gate: a second POST lands on the same graph thread,
    and re-invoking a halted thread would discard the pending interrupt.
    """
    first = open_encounter(client)
    second = open_encounter(client)
    assert first == second

    # And the gate it was halted at is still there to be answered.
    assert respond(client, first, True).status_code == 200


def test_repeated_requests_do_not_duplicate_consent_records(
    client: TestClient,
) -> None:
    """INVARIANT 5 — consent records are append-only and never revised.

    The ledger refuses a second answer for the same (encounter, user, stage),
    so a duplicate request that reached the graph would raise rather than
    overwrite. This asserts the gate stops it first, and that exactly one
    record per participant per stage exists at the end.
    """
    eid = open_encounter(client)
    for _ in range(3):
        respond(client, eid, True)
    for _ in range(3):
        consent(client, eid, True)

    ledger = get_session().ledger
    encounter = get_session().require_encounter(eid)
    for stage in (ConsentStage.ACCEPT, ConsentStage.REVEAL):
        for user_id in encounter.participants():
            matches = [
                record
                for record in ledger.records_for(eid)
                if record.user_id == user_id
                and record.stage is stage
            ]
            assert len(matches) == 1, (
                f"{user_id} has {len(matches)} records for {stage.value}; "
                "consent records must be written exactly once"
            )


# ---------------------------------------------------------------------------
# Restart recovery
# ---------------------------------------------------------------------------


def test_an_encounter_survives_losing_the_in_memory_index() -> None:
    """The weaker half of the property: the index can be dropped and rebuilt.

    This is NOT a process restart — same `SparkSession`, same connection, same
    `run_id` in memory. It proves only that `require_encounter` reads the
    checkpoint rather than the dictionary. The real thing is asserted below.
    """
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    eid = open_encounter(api)
    respond(api, eid, True)

    session = get_session()
    session._encounters.clear()          # the restart, from the inside

    assert session.checkpoint_gate(eid) == "reveal"
    body = consent(api, eid, True).json()
    assert body["outcome"] == "mutual"


# ---------------------------------------------------------------------------
# Communication Agent fidelity
# ---------------------------------------------------------------------------


def test_every_scripted_prompt_is_grounded_in_both_speakers() -> None:
    """A prompt may not claim a commonality only one person raised.

    The check is on TOPIC IDENTITY rather than on the English. Deciding whether
    two sentences are about the same subject is not something a unit test can
    do; deciding whether both speakers filed a quote under the same topic id is.

    The prompt this replaces read "you both mentioned early mornings" and cited
    a certification exam and some birdwatching as its evidence. The test in
    place at the time asserted only that two non-empty strings were present, and
    passed.
    """
    from src.api.call_fixture import SCRIPTED_PROMPTS, said_by

    assert SCRIPTED_PROMPTS
    for prompt in SCRIPTED_PROMPTS:
        local = said_by("local", prompt.topic)
        remote = said_by("remote", prompt.topic)
        assert local, f"no local quote for topic {prompt.topic!r}"
        assert remote, f"no remote quote for topic {prompt.topic!r}"
        assert prompt.grounded_in == (local, remote)


def test_a_one_sided_topic_cannot_ground_a_prompt() -> None:
    """The refusal is the feature.

    The certification exam is single-sided — the remote speaker raised it, the
    local one never did. Building a "you both..." prompt from it is exactly the
    hallucination the rule forbids, so it raises rather than returning something
    plausible.
    """
    from src.api.call_fixture import shared_grounding

    with pytest.raises(ValueError, match="never raised it"):
        shared_grounding("certification-exam")
    with pytest.raises(ValueError):
        shared_grounding("a-topic-nobody-mentioned")


def test_the_continuity_citation_quotes_the_person_it_names() -> None:
    """A brief says "she mentioned ...", so the quote must be hers.

    It previously lived in a constant named `SAID_BY_LOCAL` and was rendered as
    "She mentioned ...", attributing the user's own words to the person they had
    just met. Same class of fidelity error as an invented commonality, and just
    as invisible.
    """
    from src.api.call_fixture import CONTINUITY_CITATION, said_by

    assert CONTINUITY_CITATION == said_by("remote", "certification-exam")
    assert CONTINUITY_CITATION != said_by("local", "early-mornings")


def test_the_api_serves_the_grounded_prompts(client: TestClient) -> None:
    """And the wire carries the topic, so the claim is checkable by a client."""
    eid = open_encounter(client)
    payload = client.get(f"/api/encounters/{eid}/call-script").json()

    assert payload["prompts"]
    for prompt in payload["prompts"]:
        assert prompt["topic"]
        assert len(prompt["groundedIn"]) == 2


# ---------------------------------------------------------------------------
# Restart recovery, for real
# ---------------------------------------------------------------------------
#
# The test above drops the in-memory index inside one live session. That is not
# a restart: `run_id` is still in memory, the connection is still open, and the
# thread ids are whatever this process last chose.
#
# `run_id` is mixed into every thread id, so after `POST /api/demo/reset` the
# checkpoints were written under `enc-...#1` — and a NEW process started at
# run 0, looked under `enc-...#0`, and found nothing. LangGraph's durability was
# real the whole time; the key needed to address it was not. That made "the
# consent gate survives a restart" a true statement about the library and a
# false one about the product.
#
# These construct genuinely new `SparkSession` objects over the same SQLite
# file, which is what a restarted process looks like from the database's side.


def fresh_session() -> SparkSession:
    """A new session over the same checkpoint file — a restarted process."""
    return SparkSession()


def test_a_new_session_resumes_an_encounter_the_old_one_opened() -> None:
    first = TestClient(create_app())
    first.post("/api/demo/reset")
    eid = open_encounter(first)
    respond(first, eid, True)

    restarted = fresh_session()
    try:
        # It found the run without being told, and it knows which encounter is
        # today's. Both are read back from the database rather than assumed.
        assert restarted.current_encounter_id() == eid
        assert restarted.checkpoint_gate(eid) == "reveal"

        result = restarted.consent(eid, viewer_yes=True)
        assert reveal_permitted(restarted.ledger, result["encounter"])
    finally:
        restarted.close()


def test_recovery_still_works_after_a_demo_reset() -> None:
    """The case that was actually broken.

    A reset changes every thread id. Before the run id was persisted, a restart
    after a reset recovered nothing — and a reset happens between every take.
    """
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    api.post("/api/demo/reset")          # two, so run_id is certainly not 0
    eid = open_encounter(api)
    respond(api, eid, True)

    run_before = get_session().run_id
    assert run_before > 0

    restarted = fresh_session()
    try:
        assert restarted.run_id == run_before
        assert restarted.checkpoint_gate(eid) == "reveal"
        assert restarted.consent(eid, viewer_yes=True)["encounter"] is not None
    finally:
        restarted.close()


def test_a_completed_take_is_not_resumed_after_a_restart() -> None:
    """A finished encounter stays finished, and a reset makes old ids
    unreachable rather than replayable.

    This is the failure the run id exists to prevent: encounter ids are
    deterministic, so without it a retake would find the PREVIOUS take's
    completed checkpoint and hand back its outcome.
    """
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    finished = open_encounter(api)
    respond(api, finished, True)
    consent(api, finished, True)

    restarted = fresh_session()
    try:
        assert restarted.checkpoint_gate(finished) is None
        with pytest.raises(GateNotPending):
            restarted.consent(finished, viewer_yes=True)
    finally:
        restarted.close()

    api.post("/api/demo/reset")
    after_reset = fresh_session()
    try:
        assert after_reset.checkpoint_gate(finished) is None
        with pytest.raises(EncounterNotFound):
            after_reset.require_encounter(finished)
    finally:
        after_reset.close()


def test_the_consent_history_does_not_survive_a_restart() -> None:
    """A LIMITATION, pinned so it cannot be forgotten or overclaimed.

    The reveal itself survives: `reveal_permitted` needs `call_ended` (inside
    the checkpointed encounter) and a mutual yes at the reveal stage (which the
    resumed node records afresh). So the product behaves correctly.

    What does NOT survive is the history. `ConsentLedger` is an in-memory list
    rebuilt empty by `_build()`, so the ACCEPT-stage records written before the
    restart are gone; only the REVEAL records the resumed node wrote remain.

    CLAUDE.md invariant 5 says consent events are append-only. A log that
    empties on restart is append-only within a process and nothing more. Durable
    consent storage is already a P0 blocker in DEPLOYMENT_READINESS.md; this
    test states the behaviour exactly, so the documents and the code agree.
    """
    api = TestClient(create_app())
    api.post("/api/demo/reset")
    eid = open_encounter(api)
    respond(api, eid, True)

    before = get_session().ledger.records_for(eid)
    assert len([r for r in before if r.stage is ConsentStage.ACCEPT]) == 2

    restarted = fresh_session()
    try:
        result = restarted.consent(eid, viewer_yes=True)
        assert reveal_permitted(restarted.ledger, result["encounter"])

        stages = {r.stage for r in restarted.ledger.records_for(eid)}
        assert ConsentStage.REVEAL in stages
        assert ConsentStage.ACCEPT not in stages, (
            "the accept-stage records survived a restart — if the ledger has "
            "been made durable, update this test and the P0 item in "
            "DEPLOYMENT_READINESS.md rather than deleting the assertion"
        )
    finally:
        restarted.close()


# ---------------------------------------------------------------------------
# Continuity, now that it is behind the API
# ---------------------------------------------------------------------------
#
# `/lockins` and `/briefs` returned `[]` for the whole build, because the only
# lock-in store lived in `sim/engine.py` — behind the simulation rather than
# behind the API. That made the half of the product that justifies "plans, acts
# and adapts over time" filmable only against MockAdapter.


def test_no_lockin_exists_before_a_mutual_reveal(client: TestClient) -> None:
    """A lock-in carries a NAME. Anything that can open one without a mutual
    yes is invariant 1 with an extra step."""
    assert client.get("/api/lockins").json() == []

    eid = open_encounter(client)
    assert client.get("/api/lockins").json() == []

    respond(client, eid, True)
    assert client.get("/api/lockins").json() == []


def test_a_decline_opens_no_lockin(client: TestClient) -> None:
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, False)

    assert client.get("/api/lockins").json() == []
    assert client.get("/api/briefs").json() == []


def test_a_mutual_yes_opens_exactly_one_lockin(client: TestClient) -> None:
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)

    lockins = client.get("/api/lockins").json()
    assert len(lockins) == 1
    assert lockins[0]["person"]["displayName"]
    assert lockins[0]["state"] == "active"


def test_the_brief_cites_something_the_pair_discussed(client: TestClient) -> None:
    """A brief with nothing behind it is a reminder, and the Continuity Agent
    returns None rather than producing one. Those are dropped, not padded."""
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)

    briefs = client.get("/api/briefs").json()
    assert len(briefs) == 1
    assert briefs[0]["line"].strip()
    assert briefs[0]["lockInId"] == client.get("/api/lockins").json()[0]["lockInId"]


def test_advancing_the_clock_changes_what_continuity_says(
    client: TestClient,
) -> None:
    """The "adapts over time" claim, demonstrated rather than asserted.

    Six weeks has to fit inside a five-minute recording, so the demo control
    drives the REAL Continuity Agent forward rather than swapping in different
    copy.
    """
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)

    week_one = client.get("/api/briefs").json()[0]
    assert week_one["suggestedAction"] == "Ask how it went"
    assert client.get("/api/lockins").json()[0]["state"] == "active"

    client.post("/api/demo/advance-days?days=35")

    later = client.get("/api/briefs").json()[0]
    assert later["suggestedAction"] == "Suggest meeting"
    # And a connection with no contact for that long is quiet — the same
    # threshold the simulation uses, so the demo and the evaluation agree.
    assert client.get("/api/lockins").json()[0]["state"] == "quiet"


def test_a_reset_clears_the_lockins(client: TestClient) -> None:
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)
    assert client.get("/api/lockins").json()

    client.post("/api/demo/reset")
    assert client.get("/api/lockins").json() == []


# ---------------------------------------------------------------------------
# The Director feed
# ---------------------------------------------------------------------------


def test_the_starter_search_never_reaches_the_director_panel(
    client: TestClient,
) -> None:
    """The panel's claim is that every row is an agent doing something.

    `_first_user_with_a_candidate` probes users until it finds one whose day
    goes somewhere, emitting a pair of tool spans each time. Twenty rows of the
    demo choosing whose day to follow made that claim false, and it was the
    first thing anyone saw.

    They are marked internal, not deleted — still in the trace file for anyone
    debugging the search.
    """
    from src.api.app import _span_to_event
    from src.telemetry.trace import TRACES, is_internal

    start = len(TRACES.spans)
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)
    spans = TRACES.spans[start:]

    assert any(is_internal(s) for s in spans), "nothing was marked internal"

    visible = [
        _span_to_event(s) for s in spans if not is_internal(s)
    ]
    actions = [e.action for e in visible if e is not None]
    assert actions, "the panel would be empty"

    # THE RULE IS "NO WALL OF IDENTICAL ROWS", not "each action at most once".
    # A couple of `overlap_strength` rows are the Match Agent scoring two real
    # candidates, which is exactly what the panel is for. Twelve of them were
    # the search. So the assertion is on repetition, which is the thing that
    # was wrong.
    from collections import Counter

    worst_action, worst_count = Counter(actions).most_common(1)[0]
    assert worst_count <= 3, (
        f"{worst_action!r} appears {worst_count} times — the panel is showing "
        "a wall of near-identical rows again"
    )

    # And most of the run is machinery that a viewer should never see.
    assert len(visible) < len(spans) / 2


# ---------------------------------------------------------------------------
# Guardian, now that the check-in reaches something
# ---------------------------------------------------------------------------


def test_a_guardian_concern_is_recorded(client: TestClient) -> None:
    """The check-in used to go nowhere.

    The client had two answers that did different things on screen, and the
    `GuardianAgent` sat in `src/agents/` with its own tests and nothing
    connecting them. A safety feature that appears to listen and does not is
    worse than one that is absent.
    """
    from src.api.app import INCIDENTS

    before = len(INCIDENTS)
    eid = open_encounter(client)
    respond(client, eid, True)

    response = client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    )
    assert response.status_code == 200
    assert response.json()["recorded"] is True
    assert len(INCIDENTS) > before


def test_the_record_says_they_answered_because_they_did(client: TestClient) -> None:
    """`answered` is whether the person RESPONDED, not whether they were fine.

    Conflating the two logged "NO ANSWER — escalate per policy" against someone
    who had just pressed a button, which is exactly the record an operator has
    to be able to trust. An unanswered check-in is a timeout, and the agent is
    explicit that the silence is itself the signal.
    """
    from src.api.app import INCIDENTS

    eid = open_encounter(client)
    respond(client, eid, True)
    client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    )

    kinds = {e["kind"]: e for e in INCIDENTS._entries}
    assert kinds["check_in"]["detail"] == "answered"
    assert "NO ANSWER" not in kinds["check_in"]["detail"]
    # The concern is its own entry, distinct from the fact that they replied.
    assert "reveal withheld" in kinds["concern"]["detail"]


def test_being_fine_records_no_concern(client: TestClient) -> None:
    from src.api.app import INCIDENTS

    eid = open_encounter(client)
    respond(client, eid, True)
    concerns_before = sum(1 for e in INCIDENTS._entries if e["kind"] == "concern")

    client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": True}
    )
    concerns_after = sum(1 for e in INCIDENTS._entries if e["kind"] == "concern")
    assert concerns_after == concerns_before


def test_the_reply_does_not_claim_a_human_has_seen_it(client: TestClient) -> None:
    """The log is in memory and nobody is watching it. The wording has to be
    true today, not true once someone builds an operations desk."""
    eid = open_encounter(client)
    respond(client, eid, True)
    message = client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    ).json()["message"]

    for overclaim in ("team", "someone will", "we will contact", "reported to",
                      "moderator", "reviewed", "investigat"):
        assert overclaim not in message.lower(), f"the reply claims {overclaim!r}"


def test_the_other_party_learns_nothing_from_a_guardian_use(
    client: TestClient,
) -> None:
    """INVARIANT 2. Using Guardian must not become a signal to the other side."""
    eid = open_encounter(client)
    respond(client, eid, True)
    client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    )

    # The encounter is untouched from the other party's view, and the reveal
    # gate is still whatever it was — nothing here answers it for them.
    card = client.get(f"/api/encounters/{eid}").json()
    assert "guardian" not in json.dumps(card).lower()
    assert "concern" not in json.dumps(card).lower()


# ---------------------------------------------------------------------------
# Guardian closes the reveal path, durably
# ---------------------------------------------------------------------------
#
# The endpoint told the person "we have closed the encounter" and the server had
# done nothing at all. The reveal gate stayed pending, so:
#
#     accept -> guardian{allRight:false} -> consent{yes:true}
#     200 mutual, with the other person's name
#
# For a safety feature that is the worst class of bug, because it is
# indistinguishable from working. The closure is now a durable marker written
# BEFORE anyone is told anything, and `reveal_allowed` is the single boundary
# every identity-bearing path consults.


def close_via_guardian(client: TestClient, eid: str):
    return client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": False}
    )


def test_a_guardian_concern_stops_a_later_yes_revealing(client: TestClient) -> None:
    """The reported sequence, asserted step by step."""
    eid = open_encounter(client)
    respond(client, eid, True)
    assert close_via_guardian(client, eid).status_code == 200

    final = consent(client, eid, True)
    assert final.status_code == 200
    body = final.json()
    assert body["person"] is None
    assert body["outcome"] != "mutual"


def test_a_closed_encounter_opens_no_lockin(client: TestClient) -> None:
    """A lock-in carries a name, so it clears the safety closure too."""
    eid = open_encounter(client)
    respond(client, eid, True)
    close_via_guardian(client, eid)
    consent(client, eid, True)

    assert client.get("/api/lockins").json() == []
    assert client.get("/api/briefs").json() == []


def test_date_planning_is_refused_after_a_concern(client: TestClient) -> None:
    """Planning an evening for someone who has just said something felt off is
    the single worst thing that endpoint could do."""
    eid = open_encounter(client)
    respond(client, eid, True)
    close_via_guardian(client, eid)
    consent(client, eid, True)

    assert client.get(f"/api/encounters/{eid}/dates").status_code == 409


def test_the_closure_survives_a_genuinely_new_session(client: TestClient) -> None:
    """Durable, not in memory.

    A restart must not reopen a path that was shut for someone's safety, so the
    marker lives in the same SQLite file as the checkpoints and is read back the
    same way `run_id` is.
    """
    eid = open_encounter(client)
    respond(client, eid, True)
    close_via_guardian(client, eid)

    restarted = SparkSession()
    try:
        assert restarted.guardian_closed(eid)
        encounter = restarted.require_encounter(eid)
        assert restarted.reveal_allowed(encounter) is False
        with pytest.raises(EncounterClosed):
            restarted.consent(eid, viewer_yes=True)
    finally:
        restarted.close()


def test_being_fine_leaves_the_normal_path_alone(client: TestClient) -> None:
    """The check-in must not become a way to lose an encounter by answering it."""
    eid = open_encounter(client)
    respond(client, eid, True)
    client.post(
        f"/api/encounters/{eid}/guardian/check-in", json={"allRight": True}
    )

    body = consent(client, eid, True).json()
    assert body["outcome"] == "mutual"
    assert body["person"]["displayName"]


def test_repeating_the_concern_is_safe(client: TestClient) -> None:
    """Idempotent. A repeated submission must not weaken the closure, and must
    not error at someone who pressed a button twice."""
    eid = open_encounter(client)
    respond(client, eid, True)

    for _ in range(3):
        assert close_via_guardian(client, eid).status_code == 200

    assert consent(client, eid, True).json()["person"] is None
    assert get_session().guardian_closed(eid)


def test_the_closure_invents_no_consent_record(client: TestClient) -> None:
    """Resuming the graph would mean supplying an answer the other party never
    gave, and a fabricated consent record is not safer than an unanswered gate.

    So the gate is simply left unanswered and the closure is what stops it
    mattering. INVARIANT 5: nothing here revises an append-only record.
    """
    eid = open_encounter(client)
    respond(client, eid, True)
    before = [
        (r.user_id, r.stage, r.decision)
        for r in get_session().ledger.records_for(eid)
    ]

    close_via_guardian(client, eid)
    consent(client, eid, True)

    after = [
        (r.user_id, r.stage, r.decision)
        for r in get_session().ledger.records_for(eid)
    ]
    assert after == before, "the closure altered the consent ledger"
    assert not any(stage is ConsentStage.REVEAL for _, stage, _ in after)


def test_nothing_about_guardian_reaches_the_other_party(client: TestClient) -> None:
    """INVARIANT 2. Using Guardian must not become a signal.

    The consent payload is byte-identical to any other non-connection, and the
    card says nothing about it — so from the other side this is a decline or a
    no-show, indistinguishable as required.
    """
    eid = open_encounter(client)
    respond(client, eid, True)
    close_via_guardian(client, eid)

    closed_body = consent(client, eid, True).json()
    card = client.get(f"/api/encounters/{eid}").json()

    for payload in (closed_body, card):
        text = json.dumps(payload).lower()
        for leak in ("guardian", "concern", "safety", "incident", "flag", "report"):
            assert leak not in text, f"{leak!r} leaked to the other party"

    # And it matches an ordinary decline exactly.
    other = TestClient(create_app())
    other.post("/api/demo/reset")
    plain = open_encounter(other)
    respond(other, plain, True)
    assert consent(other, plain, False).json() == closed_body


# ---------------------------------------------------------------------------
# Demo controls: being someone, and getting another encounter
# ---------------------------------------------------------------------------
#
# There is no auth, so "which persona is this browser following" is a
# presenter's setting rather than a user's identity. These routes exist because
# the alternative is restarting the server between takes.


def test_every_persona_offered_can_be_opened(client: TestClient) -> None:
    """Each one either opens an encounter or reports an honest quiet day.

    The picker filters on the deterministic shortlist, which is cheap and makes
    no model call. The encounter then runs `select()`, which can still reject
    everyone — so 409 stays possible and is a true outcome, not a bug. What
    must never happen is a 500, and at least one persona must actually work or
    the picker is useless.
    """
    personas = client.get("/api/demo/personas").json()
    assert personas, "no persona had an eligible candidate today"

    session = get_session()
    opened = 0
    for persona in personas:
        session.act_as(persona["user_id"])
        status = client.post("/api/encounters").status_code
        assert status in (200, 409), f"{persona['user_id']} returned {status}"
        opened += status == 200
    assert opened, "every persona in the picker led to a quiet day"


def test_personas_carry_nothing_identifying(client: TestClient) -> None:
    """Only what the matcher already uses. No name, no place, no contact."""
    import json

    # Checked as KEYS, not substrings: "lat" is inside "slate-heron", and a
    # scan that cannot tell a field from a word in a handle will either miss a
    # real leak or cry wolf until somebody switches it off.
    allowed = {"user_id", "handle", "intents", "interests", "availability"}
    for persona in client.get("/api/demo/personas").json():
        assert set(persona) == allowed, f"unexpected field: {set(persona) - allowed}"


def test_acting_as_someone_else_changes_whose_day_it_is(
    client: TestClient,
) -> None:
    personas = client.get("/api/demo/personas").json()
    first = open_encounter(client)

    other = next(p for p in personas if p["user_id"] not in first)
    assert client.post(
        f"/api/demo/act-as?user_id={other['user_id']}"
    ).status_code == 200

    second = open_encounter(client)
    assert second != first


def test_acting_as_drops_the_previous_encounter_rather_than_moving_it(
    client: TestClient,
) -> None:
    """An encounter belongs to the pair it was opened for.

    Quietly re-pointing one at a different person is how a demo ends up showing
    something the system never did.
    """
    personas = client.get("/api/demo/personas").json()
    first = open_encounter(client)
    client.post(f"/api/demo/act-as?user_id={personas[-1]['user_id']}")

    assert get_session().current_encounter_id() != first


def test_an_unknown_persona_is_refused(client: TestClient) -> None:
    response = client.post("/api/demo/act-as?user_id=u-not-real")
    assert response.status_code == 404
    assert "personas" in response.json()["detail"]


def test_a_new_encounter_is_another_day(client: TestClient) -> None:
    """One encounter per person per day IS the product, and the id derives from
    the day — so "give me another" is the same thing as "let it be tomorrow"."""
    first = open_encounter(client)
    before = get_session().clock.current

    client.post("/api/demo/new-encounter")
    assert get_session().clock.current > before

    second = open_encounter(client)
    assert second != first


def test_a_new_encounter_keeps_what_was_learned(client: TestClient) -> None:
    """Unlike a reset. A presenter should be able to show the recommender
    improving ACROSS encounters, which needs the memory to survive."""
    lockin_id = None
    eid = open_encounter(client)
    respond(client, eid, True)
    consent(client, eid, True)
    lockins = client.get("/api/lockins").json()
    assert lockins
    lockin_id = lockins[0]["lockInId"]

    client.post(
        f"/api/lockins/{lockin_id}/date-plans",
        json={"budget": "free", "remember": True},
    )
    assert client.get("/api/date-memory").json()

    client.post("/api/demo/new-encounter")
    assert client.get("/api/date-memory").json(), "a new encounter wiped the memory"
    assert client.get("/api/lockins").json(), "a new encounter dropped the lock-in"


# ---------------------------------------------------------------------------
# "Receive calls from Spark"
# ---------------------------------------------------------------------------
#
# The requirement is explicit that hiding the UI is not enough: any code that
# tries to place a call must check first. So it is enforced at `connect_call`,
# the single place a call can be created, and again in the Delivery Agent
# before it even reaches the bridge.


def test_calls_are_on_by_default(client: TestClient) -> None:
    """The daily call IS the product. Off has to be a choice, not a default."""
    assert client.get("/api/settings").json()["allowCalls"] is True


def test_turning_calls_off_stops_the_call_happening(client: TestClient) -> None:
    client.get("/api/settings")
    client.put("/api/settings", json={"allowCalls": False})

    eid = open_encounter(client)
    body = respond(client, eid, True).json()
    assert body["connected"] is False
    assert body["state"] == "ABANDONED"


def test_a_disabled_call_looks_exactly_like_a_no_show(client: TestClient) -> None:
    """INVARIANT 2. A privacy setting must not become a signal about the person
    who set it — the other party has to see what a no-show looks like."""
    client.get("/api/settings")
    client.put("/api/settings", json={"allowCalls": False})
    disabled = respond(client, open_encounter(client), True).json()

    other = TestClient(create_app())
    other.post("/api/demo/reset")
    declined = respond(other, open_encounter(other), False).json()

    assert disabled == declined


def test_turning_calls_back_on_restores_them(client: TestClient) -> None:
    client.get("/api/settings")
    client.put("/api/settings", json={"allowCalls": False})
    client.put("/api/settings", json={"allowCalls": True})

    body = respond(client, open_encounter(client), True).json()
    assert body["connected"] is True


def test_the_bridge_itself_refuses_not_just_the_agent(client: TestClient) -> None:
    """Defence in depth. If a future caller forgets the check, the one place a
    call can be created still will not make one."""
    from src.mcp.registry import ToolFailure
    from src.mcp.services import connect_call

    with pytest.raises(ToolFailure, match="turned off calls"):
        connect_call(
            "enc-x", both_accepted=True,
            started_at="2026-09-03T21:00:00", calls_allowed=False,
        )


def test_a_partial_update_leaves_other_settings_alone(client: TestClient) -> None:
    """One screen toggling one switch must not silently reset the others."""
    client.get("/api/settings")
    client.put("/api/settings", json={"allowDateSuggestions": False})
    client.put("/api/settings", json={"allowCalls": False})

    settings = client.get("/api/settings").json()
    assert settings["allowCalls"] is False
    assert settings["allowDateSuggestions"] is False


def test_settings_and_the_encounter_agree_about_who_you_are(
    client: TestClient,
) -> None:
    """The bug this fixes: settings resolved the viewer one way and the
    encounter another, so turning calls off turned them off for somebody else
    and the call connected anyway. A preference applied to the wrong person is
    worse than one not applied at all."""
    session = get_session()
    client.get("/api/settings")
    viewer = session.viewer_user_id()

    eid = open_encounter(client)
    assert session.require_encounter(eid).user_a == viewer


def test_profile_update_writes_the_profile_the_match_agent_reads(
    client: TestClient,
) -> None:
    """Onboarding's final write must not land in a UI-only profile copy."""
    session = get_session()
    viewer = session.viewer_user_id()

    response = client.put(
        "/api/profile",
        json={
            "intents": ["friends", "partner_long_term"],
            "interests": ["coffee", "reading"],
            "values": ["honesty", "kindness"],
            "personality": "optimistic, independent",
            "languages": ["english", "mandarin"],
        },
    )

    assert response.status_code == 200, response.text
    matchable = session.user(viewer).profile
    assert [intent.value for intent in matchable.intents] == [
        "friends",
        "partner_long_term",
    ]
    assert matchable.interests == ["coffee", "reading"]
    assert matchable.values == ["honesty", "kindness"]
    assert matchable.personality == "optimistic, independent"
    assert matchable.languages == ["english", "mandarin"]
