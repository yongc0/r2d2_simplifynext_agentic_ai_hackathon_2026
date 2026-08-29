"""The supervisor graph, and the property the consent gate depends on.

The headline test here is `test_the_graph_survives_a_restart_mid_consent`. In
production the two answers to "may we swap names" can be hours or days apart,
and the process that asked the question will not be the process that hears the
answer. If a restart lost the thread, the gate would have to be replaced by
something that stores approval in a database and checks a flag — which is
exactly the design §11.4 rejects.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date as Date

import pytest
from langgraph.graph import END
from langgraph.types import Command

from src.agents.continuity import ContinuityAgent
from src.agents.delivery import EncounterDelivery
from src.agents.match import MatchAgent
from src.clock import SimClock
from src.graph.state import SparkRuntime
from src.graph.supervisor import (
    build_encounter_graph,
    pending_gate,
    sqlite_checkpointer,
)
from src.ids import encounter_id
from src.mcp.services import WORLD
from src.schemas.core import Encounter, EncounterState, Overlap, TimeBucket

DAY = Date(2026, 9, 1)


def _runtime(client, trust, ledger, users) -> SparkRuntime:
    return SparkRuntime(
        client=client,
        trust=trust,
        ledger=ledger,
        delivery=EncounterDelivery(client=client, ledger=ledger),
        match=MatchAgent(client=client, trust=trust),
        continuity=ContinuityAgent(client=client),
        clock=SimClock(DAY),
        users=dict(users),
        encounter_counts=Counter(),
    )


@pytest.fixture
def seeded(users):
    """Put the two fixture users in each other's overlap pool for the day."""
    ids = sorted(users)
    WORLD.overlaps[DAY] = [
        Overlap(
            user_a=ids[0], user_b=ids[1], cell_id="cell-01",
            time_bucket=TimeBucket.EVENING, date=DAY,
        )
    ]
    WORLD.availability[ids[0]] = [TimeBucket.EVENING]
    WORLD.availability[ids[1]] = [TimeBucket.EVENING]
    from src.mcp.services import index_overlaps

    index_overlaps()
    return users


def _fresh_encounter(users) -> tuple[Encounter, dict]:
    starter = sorted(users)[0]
    eid = encounter_id(DAY.isoformat(), starter, "pending")
    encounter = Encounter(
        id=eid, match_id="m", day=DAY, user_a=starter, user_b=f"{starter}-tbd"
    )
    state = {
        "encounter": encounter,
        "users": {starter: users[starter]},
        "day": DAY,
        "trail": [],
    }
    return encounter, state


# ---------------------------------------------------------------------------
# The whole path
# ---------------------------------------------------------------------------


def test_an_encounter_runs_from_profiled_to_locked_in(seeded, client, trust, ledger):
    """Milestone 1's acceptance test: the full path, with a trace."""
    runtime = _runtime(client, trust, ledger, seeded)
    app = build_encounter_graph(runtime)
    encounter, state = _fresh_encounter(seeded)
    config = {"configurable": {"thread_id": encounter.id}}

    result = app.invoke(state, config)
    gate = pending_gate(result)
    assert gate is not None and gate.gate == "accept"

    peer = result["encounter"].user_b
    starter = result["encounter"].user_a
    result = app.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    assert pending_gate(result).gate == "reveal"

    result = app.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    assert result["encounter"].state is EncounterState.LOCKED_IN
    assert result["encounter"].call_duration_s == 180
    assert result["encounter"].trace_id


def test_a_decline_at_the_first_gate_ends_the_encounter_silently(
    seeded, client, trust, ledger
):
    runtime = _runtime(client, trust, ledger, seeded)
    app = build_encounter_graph(runtime)
    encounter, state = _fresh_encounter(seeded)
    config = {"configurable": {"thread_id": encounter.id}}

    result = app.invoke(state, config)
    starter = result["encounter"].user_a
    peer = result["encounter"].user_b
    result = app.invoke(Command(resume={starter: "yes", peer: "no"}), config)

    assert result["encounter"].state is EncounterState.ABANDONED
    # The reason exists for the operator, and appears in no view.
    assert result["terminal_reason"]
    assert "outcome" not in result.get("views", {})


def test_a_non_mutual_reveal_closes_without_an_identity(seeded, client, trust, ledger):
    runtime = _runtime(client, trust, ledger, seeded)
    app = build_encounter_graph(runtime)
    encounter, state = _fresh_encounter(seeded)
    config = {"configurable": {"thread_id": encounter.id}}

    result = app.invoke(state, config)
    starter, peer = result["encounter"].user_a, result["encounter"].user_b
    result = app.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    result = app.invoke(Command(resume={starter: "yes", peer: "no"}), config)

    assert result["encounter"].state is EncounterState.CLOSED
    assert result["encounter"].revealed is False
    for view in result["views"]["outcome"].values():
        assert "display_name" not in view
        assert view["headline"] == "That conversation has closed."


# ---------------------------------------------------------------------------
# Durability — the property the consent gate rests on
# ---------------------------------------------------------------------------


def test_the_graph_survives_a_restart_mid_consent(
    seeded, client, trust, ledger, scratch_dir
):
    """Halt at the reveal gate, destroy everything, resume from disk.

    The connection is closed and both the graph object and the saver are
    rebuilt from scratch, which is as close to a process restart as a test can
    get without spawning one. In production the two answers can be days apart.
    """
    db = scratch_dir / "checkpoints.sqlite"
    runtime = _runtime(client, trust, ledger, seeded)
    encounter, state = _fresh_encounter(seeded)
    config = {"configurable": {"thread_id": encounter.id}}

    saver, conn = sqlite_checkpointer(db)
    app = build_encounter_graph(runtime, checkpointer=saver)
    result = app.invoke(state, config)
    starter, peer = result["encounter"].user_a, result["encounter"].user_b
    result = app.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    assert pending_gate(result).gate == "reveal"
    conn.close()                                     # the process dies here
    del app, saver

    # --- a new process opens the same file ---------------------------
    saver2, conn2 = sqlite_checkpointer(db)
    app2 = build_encounter_graph(runtime, checkpointer=saver2)
    snapshot = app2.get_state(config)
    assert snapshot.next == ("consent_gate",)
    assert snapshot.interrupts, "the pending interrupt did not survive the restart"
    assert snapshot.values["encounter"].call_duration_s == 180

    resumed = app2.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    assert resumed["encounter"].state is EncounterState.LOCKED_IN
    conn2.close()


def test_nothing_happens_before_the_interrupt_in_a_gate_node():
    """A resumed node re-runs from the top, so a side effect above the
    `interrupt()` call would happen twice — once when the gate opened and once
    when it closed. Both gates must call `interrupt` first."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/graph/nodes.py").read_text(encoding="utf-8"))
    checked = 0
    for node in ast.walk(tree):
        # The gate NODES, not the `make_*` factories that build them.
        if (
            not isinstance(node, ast.FunctionDef)
            or not node.name.endswith("_gate")
            or node.name.startswith("make_")
        ):
            continue
        checked += 1
        body = node.body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]                          # skip the docstring
        assert "interrupt" in ast.dump(body[0]), (
            f"{node.name} does something before calling interrupt(); on resume "
            "that side effect happens twice"
        )
    assert checked == 2, f"expected exactly two gate nodes, found {checked}"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_every_silent_ending_routes_to_end(seeded, client, trust, ledger):
    """`ABANDONED` and `CLOSED` are terminal (§14) and lead nowhere else."""
    from src.graph.supervisor import (
        _after_accept_gate, _after_call, _after_outcome, _after_select,
    )

    encounter, _ = _fresh_encounter(seeded)
    encounter.state = EncounterState.ABANDONED
    state = {"encounter": encounter}
    assert _after_select(state) is END
    assert _after_accept_gate(state) is END
    assert _after_call(state) is END

    encounter.state = EncounterState.CLOSED
    assert _after_outcome(state) is END


def test_the_state_machine_refuses_an_illegal_transition(seeded):
    encounter, _ = _fresh_encounter(seeded)
    with pytest.raises(ValueError, match="illegal encounter transition"):
        encounter.transition_to(EncounterState.REVEALED)
