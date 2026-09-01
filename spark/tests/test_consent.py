"""The invariants. These are the product.

CLAUDE.md: **never delete or weaken one of these tests to make a feature pass.
If a test blocks you, the feature is wrong.**

One section per invariant:

  1  no identity, photo or number before both parties say yes after the call
  2  a decline emits no observable signal to the other party
  3  no distance, place name, coordinate or map position is ever rendered
  4  the call terminates at 180 seconds regardless of state
  5  consent events are append-only, never joined into anything user-visible
  6  no model decides any of the above
"""

from __future__ import annotations

import ast
import itertools
from datetime import datetime
from pathlib import Path

import pytest

from src.config import SETTINGS
from src.mcp.registry import MCPClient, ToolError
from src.safety.consent import (
    ConsentLedger,
    ConsentViolation,
    RevealRefused,
    build_close_out,
    build_reveal,
    is_mutual_yes,
    reveal_permitted,
)
from src.safety.guardrails import (
    AnonymityLeak,
    IDENTITIES,
    render,
    screen_outbound,
)
from src.schemas.core import ConsentDecision, ConsentStage, EncounterState
from src.schemas.views import AnonymousPeer, CloseOutView, EncounterCard, RevealView
from tests.conftest import CALL_ENDED

ANSWERS = (ConsentDecision.YES, ConsentDecision.NO, ConsentDecision.TIMEOUT)


def _answer(ledger, encounter, user_id, decision, stage=ConsentStage.REVEAL):
    """Record an answer, treating TIMEOUT as "never answered" — which is what
    a timeout is: an absent record, not a written one."""
    if decision is ConsentDecision.TIMEOUT:
        return
    ledger.record(encounter.id, user_id, stage, decision, datetime(2026, 9, 1, 20, 0))


# ===========================================================================
# INVARIANT 1 — no identity before a mutual yes
# ===========================================================================


@pytest.mark.parametrize(
    "answer_a,answer_b",
    [pair for pair in itertools.product(ANSWERS, ANSWERS) if pair != (ConsentDecision.YES,) * 2],
)
def test_reveal_refused_for_every_non_mutual_combination(
    ledger, encounter, users, answer_a, answer_b
):
    """INVARIANT 1. Eight of the nine combinations must refuse.

    Parametrised rather than written out, so a future decision value cannot be
    added without this test covering it.
    """
    _answer(ledger, encounter, encounter.user_a, answer_a)
    _answer(ledger, encounter, encounter.user_b, answer_b)

    assert reveal_permitted(ledger, encounter) is False
    with pytest.raises(RevealRefused):
        build_reveal(
            ledger,
            encounter,
            viewer_id=encounter.user_a,
            other=users[encounter.user_b],
            lockin_id="lock-test",
            at=CALL_ENDED,
        )


def test_reveal_permitted_only_on_mutual_yes(ledger, encounter, users):
    """INVARIANT 1, the ninth combination — the only one that opens."""
    _answer(ledger, encounter, encounter.user_a, ConsentDecision.YES)
    _answer(ledger, encounter, encounter.user_b, ConsentDecision.YES)

    assert reveal_permitted(ledger, encounter) is True
    view = build_reveal(
        ledger,
        encounter,
        viewer_id=encounter.user_a,
        other=users[encounter.user_b],
        lockin_id="lock-test",
        at=CALL_ENDED,
    )
    assert isinstance(view, RevealView)
    assert view.display_name == users[encounter.user_b].identity.display_name


def test_reveal_refused_before_the_call_even_with_two_yeses(ledger, encounter, users):
    """A yes to the *notification* is not a yes to a reveal.

    Both stages exist precisely so that agreeing to talk cannot be silently
    upgraded into agreeing to be identified.
    """
    encounter.call_ended = None
    _answer(ledger, encounter, encounter.user_a, ConsentDecision.YES, ConsentStage.ACCEPT)
    _answer(ledger, encounter, encounter.user_b, ConsentDecision.YES, ConsentStage.ACCEPT)

    assert reveal_permitted(ledger, encounter) is False
    with pytest.raises(RevealRefused):
        build_reveal(
            ledger, encounter, viewer_id=encounter.user_a,
            other=users[encounter.user_b], lockin_id="lock-test", at=CALL_ENDED,
        )


def test_the_anonymous_peer_has_nowhere_to_put_an_identity():
    """INVARIANT 1, structurally.

    Not "we remember not to fill it in" — there is no field. If someone adds
    one, this fails before any behaviour does.
    """
    forbidden = {
        "name", "display_name", "first_name", "phone", "number", "email",
        "photo", "picture", "image", "avatar", "age", "location", "place",
        "distance", "cell", "cell_id", "coordinates", "lat", "lon",
    }
    assert forbidden.isdisjoint(AnonymousPeer.model_fields)
    assert forbidden.isdisjoint(EncounterCard.model_fields)
    assert forbidden.isdisjoint(CloseOutView.model_fields)


def test_reveal_view_is_only_constructible_through_the_gate():
    """INVARIANT 1. `build_reveal` must be the sole construction site.

    Checked by reading the source rather than by convention: any other module
    instantiating `RevealView` is a way round the gate.
    """
    src = Path("src")
    offenders = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "RevealView"
                and path.as_posix() != "src/safety/consent.py"
            ):
                offenders.append(f"{path.as_posix()}:{node.lineno}")
    assert not offenders, (
        "RevealView is constructed outside src/safety/consent.py at "
        f"{offenders}. Identity-bearing views may only be built by "
        "build_reveal(), which requires a mutual yes."
    )


# ===========================================================================
# INVARIANT 2 — a decline emits no observable signal
# ===========================================================================


@pytest.mark.parametrize("my_answer", [ConsentDecision.YES, ConsentDecision.NO])
@pytest.mark.parametrize("their_answer", ANSWERS)
def test_close_out_is_identical_whatever_the_other_person_did(
    ledger, encounter, my_answer, their_answer
):
    """INVARIANT 2, the central case.

    Fix what I did. Vary what they did across yes / no / never answered. What I
    see must be byte-identical every time — including the timestamp, because a
    delay that varied with their answer would be the clock saying what the
    words refuse to.

    (When both said yes the encounter reveals instead, so that combination is
    excluded by the assertion below rather than by not testing it.)
    """
    if my_answer is ConsentDecision.YES and their_answer is ConsentDecision.YES:
        pytest.skip("a mutual yes reveals; this test is about every other ending")

    _answer(ledger, encounter, encounter.user_a, my_answer)
    _answer(ledger, encounter, encounter.user_b, their_answer)
    assert reveal_permitted(ledger, encounter) is False

    view = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)
    reference = CloseOutView(
        encounter_id=encounter.id,
        available_at=CALL_ENDED
        + __import__("datetime").timedelta(
            minutes=SETTINGS.rules.close_out_delay_minutes
        ),
    )
    assert view.model_dump() == reference.model_dump()


def test_close_out_cannot_read_the_other_answer(ledger, encounter):
    """INVARIANT 2, enforced by the signature.

    `build_close_out` takes an id, a viewer and the call-end time. It is never
    handed the ledger, the encounter, or the other party's decision, so it
    cannot vary with them however the body is later edited.
    """
    import inspect

    parameters = set(inspect.signature(build_close_out).parameters)
    assert parameters == {"encounter_id", "viewer_id", "call_ended"}, (
        "build_close_out has grown a parameter. If any argument can carry the "
        "other party's answer, INVARIANT 2 is no longer structural."
    )


def test_both_parties_see_the_same_close_out(ledger, encounter):
    """Neither participant's view differs from the other's.

    A view that differed between them would be a channel between them: A could
    learn something about B by comparing notes, which is the same leak by a
    slower route.
    """
    _answer(ledger, encounter, encounter.user_a, ConsentDecision.YES)
    _answer(ledger, encounter, encounter.user_b, ConsentDecision.NO)

    a = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)
    b = build_close_out(encounter.id, encounter.user_b, encounter.call_ended)
    assert a.model_dump() == b.model_dump()


def test_close_out_carries_no_count_and_no_status(ledger, encounter):
    """No "3 people passed", no "still pending", no "they were not ready"."""
    view = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)
    text = " ".join(str(v) for v in view.model_dump().values()).lower()
    for leak in ("declin", "pending", "waiting", "they ", "other person", "not ready"):
        assert leak not in text, f"the close-out says something about the other party: {leak!r}"


def test_abandoned_and_closed_are_both_silent_terminals():
    """§14: both are normal terminal states, and neither may say why."""
    from src.schemas.core import SILENT_TERMINAL_STATES

    assert SILENT_TERMINAL_STATES == frozenset(
        {EncounterState.CLOSED, EncounterState.ABANDONED}
    )


# ===========================================================================
# INVARIANT 3 — no distance, place, coordinate or map position
# ===========================================================================


@pytest.mark.parametrize(
    "text",
    [
        "They were 300 m away.",
        "About 1.2 km from you.",
        "You were both at Raffles Place.",
        "1.2903, 103.8519",
        "Someone nearby crossed your path.",
        "They are 15 minutes away.",
        "You work in the same building.",
        "They are currently at the office.",
        "matched on cell_id cell-07",
    ],
)
def test_location_is_never_rendered(users, text):
    """INVARIANT 3. Every one of these must be refused."""
    IDENTITIES.register_places(["Raffles Place", "Tanjong Pagar"])
    verdict = screen_outbound(text, "u-alice", subject_id="u-bob")
    assert verdict.allowed is False, f"a location leak was allowed through: {text!r}"
    assert "location" in verdict.categories


@pytest.mark.parametrize(
    "text",
    [
        "You have both mentioned climbing.",
        "Your paths crossed more than once this week.",
        "You are both free in the evening.",
        "That conversation has closed.",
    ],
)
def test_ordinary_copy_is_not_blocked(users, text):
    """The guardrail must not cry wolf.

    A filter that blocks normal sentences gets switched off, and then it
    protects nobody. These are the strings the product actually sends.
    """
    IDENTITIES.register_places(["Raffles Place"])
    assert screen_outbound(text, "u-alice", subject_id="u-bob").allowed is True


def test_render_raises_rather_than_quietly_redacting(users):
    """A leak that is silently patched over is a leak nobody fixes."""
    with pytest.raises(AnonymityLeak):
        render("They were 200 m away.", "u-alice", subject_id="u-bob", context="test")


def test_identity_is_blocked_until_that_specific_pair_reveals(users):
    """A reveal opens one pair, not the address book."""
    assert screen_outbound("Torin was funny.", "u-alice", subject_id="u-bob").allowed is False
    IDENTITIES.mark_revealed("u-alice", "u-bob")
    assert screen_outbound("Torin was funny.", "u-alice", subject_id="u-bob").allowed is True
    # A third party is still hidden from the same viewer.
    assert screen_outbound("Torin was funny.", "u-carol", subject_id="u-dave").allowed is False


# ===========================================================================
# INVARIANT 4 — the call stops at 180 seconds
# ===========================================================================


def test_the_call_stops_at_180_seconds(client, encounter, users):
    """INVARIANT 4. The bridge decides the duration and the config sets it."""
    result = client.call(
        "spark-voice",
        "connect_call",
        encounter_id=encounter.id,
        both_accepted=True,
        started_at="2026-09-01T19:00:00",
    )
    assert result["duration_s"] == SETTINGS.rules.call_seconds == 180
    assert result["ended_reason"] == "time_limit"


def test_duration_is_not_a_parameter_of_the_bridge():
    """There is no argument that asks for a longer call.

    Checked on the signature, because the day someone adds `duration_s=` is the
    day the invariant becomes a suggestion.

    TWO ASSERTIONS, and the second is the one that matters. The allowlist
    catches ANY new parameter and forces whoever added it to come here and
    justify it — that is the test doing its job, not an obstacle. The name check
    below states the actual invariant, so widening the list can never quietly
    admit a duration.

    `calls_allowed` was added deliberately, in the same shape as
    `both_accepted`: the bridge is handed permission and refuses without it,
    rather than looking it up. It is "receive calls from Spark" enforced at the
    one place a call can be created, so turning the setting off removes the
    capability instead of hiding a button.
    """
    import inspect

    from src.mcp.services import connect_call

    parameters = set(inspect.signature(connect_call).parameters)
    assert parameters == {
        "encounter_id",
        "both_accepted",
        "started_at",
        "calls_allowed",
    }

    # The invariant itself, independent of the list above.
    for name in parameters:
        assert not any(
            word in name.lower()
            for word in ("duration", "seconds", "length", "extend", "minutes")
        ), f"{name!r} looks like it could ask for a longer call"


def test_the_bridge_refuses_without_dual_acceptance(client, encounter):
    """No call happens on one person's yes."""
    with pytest.raises(ToolError):
        client.call(
            "spark-voice",
            "connect_call",
            encounter_id=encounter.id,
            both_accepted=False,
            started_at="2026-09-01T19:00:00",
        )


def test_delivery_rejects_an_overlong_call(client, ledger, encounter, users, monkeypatch):
    """Defence in depth: if the bridge ever returned 200 seconds, delivery voids
    the call rather than accepting it."""
    from src.agents.delivery import DeliveryRefused, EncounterDelivery

    delivery = EncounterDelivery(client=client, ledger=ledger)
    for user_id in encounter.participants():
        delivery.record_accept(
            encounter, user_id, ConsentDecision.YES, datetime(2026, 9, 1, 18, 30)
        )

    def overlong(*_args, **_kwargs):
        return {"duration_s": 200, "encounter_id": encounter.id}

    monkeypatch.setattr(client, "call", overlong)
    with pytest.raises(DeliveryRefused, match="INVARIANT 4"):
        delivery.connect(encounter, datetime(2026, 9, 1, 19, 0))


# ===========================================================================
# INVARIANT 5 — consent events are append-only
# ===========================================================================


def test_a_consent_record_cannot_be_revised(ledger, encounter):
    """INVARIANT 5. An editable consent record is not a consent record."""
    ledger.record(
        encounter.id, encounter.user_a, ConsentStage.REVEAL,
        ConsentDecision.NO, datetime(2026, 9, 1, 20, 0),
    )
    with pytest.raises(ConsentViolation):
        ledger.record(
            encounter.id, encounter.user_a, ConsentStage.REVEAL,
            ConsentDecision.YES, datetime(2026, 9, 1, 20, 5),
        )


def test_reading_the_ledger_hands_back_copies(ledger, encounter):
    """A caller cannot reach in and edit history."""
    ledger.record(
        encounter.id, encounter.user_a, ConsentStage.REVEAL,
        ConsentDecision.NO, datetime(2026, 9, 1, 20, 0),
    )
    records = ledger.records_for(encounter.id)
    records[0].decision  # touch it
    object.__setattr__(records[0], "decision", ConsentDecision.YES)
    assert ledger.records_for(encounter.id)[0].decision is ConsentDecision.NO


def test_the_ledger_reaches_a_user_only_as_one_boolean(ledger, encounter, users):
    """INVARIANT 5. Consent events are never joined into anything user-visible.

    The only ledger-derived value that influences a view is `is_mutual_yes`,
    and it only ever opens a reveal both people asked for.
    """
    _answer(ledger, encounter, encounter.user_a, ConsentDecision.YES)
    _answer(ledger, encounter, encounter.user_b, ConsentDecision.NO)

    view = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)
    rendered = str(view.model_dump())
    for record in ledger.records_for(encounter.id):
        assert record.decision.value not in rendered
        assert record.user_id not in rendered


def test_timeout_and_decline_are_indistinguishable_downstream(ledger, encounter):
    """An absent answer and a "no" must behave identically from here on."""
    _answer(ledger, encounter, encounter.user_a, ConsentDecision.YES)
    _answer(ledger, encounter, encounter.user_b, ConsentDecision.NO)
    declined = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)

    fresh = ConsentLedger()
    fresh.record(
        encounter.id, encounter.user_a, ConsentStage.REVEAL,
        ConsentDecision.YES, datetime(2026, 9, 1, 20, 0),
    )                                                # B never answered at all
    assert is_mutual_yes(fresh, encounter, ConsentStage.REVEAL) is False
    timed_out = build_close_out(encounter.id, encounter.user_a, encounter.call_ended)
    assert declined.model_dump() == timed_out.model_dump()


# ===========================================================================
# INVARIANT 6 — no model decides any of the above
# ===========================================================================


def test_the_safety_package_never_imports_a_model():
    """INVARIANT 6, checked against the imports rather than trusted.

    A model must never be the only thing standing between a stranger and
    someone's identity, so the package that decides consent, eligibility and
    reveal may not reach a model at all.
    """
    forbidden = {"src.models", "langchain_groq", "langchain_aws", "groq", "boto3"}
    offenders: list[str] = []
    for path in Path("src/safety").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            for name in names:
                if any(name.startswith(bad) for bad in forbidden):
                    offenders.append(f"{path.as_posix()}:{node.lineno} imports {name}")
    assert not offenders, (
        "the safety package reaches a model: " + "; ".join(offenders)
    )


def test_encounter_delivery_never_imports_a_model():
    """The agent that owns the call and both gates is deterministic too."""
    forbidden = ("src.models", "langchain", "groq", "boto3")
    tree = ast.parse(Path("src/agents/delivery.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith(forbidden), (
                f"src/agents/delivery.py imports {node.module}; Encounter "
                "Delivery is DETERMINISTIC (§13.3)"
            )


def test_eligibility_is_ordinary_python(alice, bob, trust):
    """Eligibility is a function with a reason, not a probability."""
    from src.agents.match import eligible

    assert eligible(alice, bob, __import__("datetime").date(2026, 9, 1), trust, 5) is None
    trust.block(alice.id, bob.id)
    why_not = eligible(alice, bob, __import__("datetime").date(2026, 9, 1), trust, 5)
    assert why_not is not None and "block" in why_not.reason
