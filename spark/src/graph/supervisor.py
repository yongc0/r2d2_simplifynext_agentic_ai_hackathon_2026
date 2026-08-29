"""The Supervisor — organisers' class: **Orchestration** (Coordinate & Integrate).

This is the architecture slide. Open it beside slide 5 and they should match.

    START
      |
      v
    pool ......... spark-overlap: whose path crossed yours today
      |
      v
    select ....... Match Agent (Decision-Support) -> one candidate, or nobody
      |
      +--(nobody)--> END
      |
      v
    notify ....... Encounter Delivery (Transaction): two anonymous cards
      |
      v
  [ accept_gate ] INTERRUPT — the graph halts until both answer
      |
      +--(not both)--> END          (ABANDONED, and silent)
      |
      v
    call ......... spark-voice: three minutes, hard stop
      |
      +--(bridge failed)--> END     (ABANDONED, and silent)
      |
      v
  [ consent_gate ] INTERRUPT — the graph halts until both answer privately
      |
      v
    outcome ...... mutual yes -> REVEALED, otherwise CLOSED (and silent)
      |
      +--(closed)--> END
      |
      v
    lockin ....... the connection the Continuity Agent then owns for weeks
      |
      v
    END

Two things are worth noticing in the code below rather than in this comment.

**The gates are graph nodes, not application logic.** `interrupt()` suspends
the whole graph and writes a checkpoint. There is no `if approved:` anywhere,
because there is no execution path that reaches `call` without a resume that
carried two answers. That property is structural, and it is the reason consent
is modelled as an interrupt rather than as a screen.

**Every edge out of a gate that is not "proceed" goes to END.** `ABANDONED` and
`CLOSED` are normal terminal states (§14) and produce no observable signal to
either party.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.graph import nodes
from src.graph.state import EncounterGraphState, SparkRuntime
from src.schemas.core import EncounterState

def _checkpoint_types() -> list[type]:
    """Every schema class allowed to be revived from a checkpoint.

    LangGraph will not deserialise an unregistered type — rightly, since a
    checkpoint is untrusted input. Enumerated from the three schema modules
    rather than hand-listed, so adding a model does not silently break a
    week-old thread that happens to carry it.
    """
    import inspect

    from src.schemas import agents, core, views

    allowed: list[type] = []
    for module in (core, agents, views):
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__:
                allowed.append(obj)
    return allowed


def _serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_checkpoint_types())


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _after_select(state: EncounterGraphState) -> str:
    """A day with nobody eligible ends here, and that is a normal day."""
    return END if state["encounter"].state is EncounterState.ABANDONED else "notify"


def _after_accept_gate(state: EncounterGraphState) -> str:
    return END if state["encounter"].state is EncounterState.ABANDONED else "call"


def _after_call(state: EncounterGraphState) -> str:
    return END if state["encounter"].state is EncounterState.ABANDONED else "consent_gate"


def _after_outcome(state: EncounterGraphState) -> str:
    return "lockin" if state["encounter"].state is EncounterState.REVEALED else END


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def build_encounter_graph(runtime: SparkRuntime, checkpointer=None):
    """Compile the supervisor.

    `checkpointer` defaults to an in-memory saver, which is right for a test
    and for one CLI run. `sqlite_checkpointer()` gives the durable one that
    survives a process restart — the property the consent gate needs in
    production, where the two answers can be days apart.
    """
    graph = StateGraph(EncounterGraphState)

    graph.add_node("pool", nodes.make_pool_node(runtime))
    graph.add_node("select", nodes.make_select_node(runtime))
    graph.add_node("notify", nodes.make_notify_node(runtime))
    graph.add_node("accept_gate", nodes.make_accept_gate(runtime))
    graph.add_node("call", nodes.make_call_node(runtime))
    graph.add_node("consent_gate", nodes.make_consent_gate(runtime))
    graph.add_node("outcome", nodes.make_outcome_node(runtime))
    graph.add_node("lockin", nodes.make_lockin_node(runtime))

    graph.add_edge(START, "pool")
    graph.add_edge("pool", "select")
    graph.add_conditional_edges("select", _after_select, {"notify": "notify", END: END})
    graph.add_edge("notify", "accept_gate")
    graph.add_conditional_edges("accept_gate", _after_accept_gate, {"call": "call", END: END})
    graph.add_conditional_edges(
        "call", _after_call, {"consent_gate": "consent_gate", END: END}
    )
    graph.add_edge("consent_gate", "outcome")
    graph.add_conditional_edges("outcome", _after_outcome, {"lockin": "lockin", END: END})
    graph.add_edge("lockin", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver(serde=_serde()))


def sqlite_checkpointer(path: Path) -> tuple[SqliteSaver, sqlite3.Connection]:
    """A durable checkpointer, and the connection to close when done.

    Returned as a pair rather than a context manager because the whole point is
    that the saver outlives the block that made it: the graph halts at a gate,
    the process exits, and a later process opens the same file and resumes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn, serde=_serde()), conn


@dataclass
class GateRequest:
    """What a halted graph is waiting for.

    Lifted out of the raw interrupt payload so a client — the CLI, a test, an
    AG-UI surface — reads it as a typed thing rather than digging through
    LangGraph internals.
    """

    gate: str
    encounter_id: str
    question: str
    participants: list[str]


def pending_gate(result: dict) -> GateRequest | None:
    """The gate a graph invocation stopped at, if it stopped at one."""
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if not interrupts:
        return None
    payload = interrupts[0].value
    return GateRequest(
        gate=payload.get("gate", "unknown"),
        encounter_id=payload.get("encounter_id", ""),
        question=payload.get("question", ""),
        participants=list(payload.get("participants", [])),
    )


def render_graph_ascii(runtime: SparkRuntime) -> str:
    """Draw the compiled graph. Printed by the CLI so the structure is visible
    without reading the code — and so what is on the slide is what is running."""
    app = build_encounter_graph(runtime)
    try:
        return app.get_graph().draw_ascii()
    except Exception as exc:                                # grandalf not installed
        return (
            f"(graph diagram unavailable: {exc}. The structure is in the "
            "docstring at the top of src/graph/supervisor.py.)"
        )
