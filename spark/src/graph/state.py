"""The graph's state, and the runtime the nodes are built over.

`EncounterState` — the one the state machine transitions through — lives in
`src/schemas/core.py` with the rest of the domain, because it is a property of
an encounter rather than of the graph. This file holds what LangGraph carries
between nodes.

The state is deliberately small. Everything durable is in the `Encounter`; the
rest is what one run of the graph needs to remember while it is in flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Annotated, Any, TypedDict

from src.agents.continuity import ContinuityAgent
from src.agents.delivery import EncounterDelivery
from src.agents.match import MatchPolicy
from src.clock import SimClock
from src.mcp.registry import MCPClient
from src.safety.consent import ConsentLedger
from src.safety.trust import TrustAndSafety
from src.schemas.core import Encounter, User


def _append(existing: list, new: list) -> list:
    """Reducer for the audit trail: nodes add, nothing overwrites."""
    return existing + new


class EncounterGraphState(TypedDict, total=False):
    """What travels between nodes.

    `encounter` is the unit of state (§11.1) and is checkpointed, so a thread
    that halts at the consent gate on a Tuesday can be resumed on the Thursday
    — including across a process restart, which `tests/test_graph.py` proves.
    """

    encounter: Encounter
    #: The two users, by id. Identities live on these objects and are never
    #: rendered — the guardrail is what makes that a guarantee rather than a
    #: habit.
    users: dict[str, User]
    day: Date
    #: Candidate ids from `spark-overlap` for the day.
    pool: list[str]
    #: The Match Agent's decision, as a plain dict for checkpoint friendliness.
    decision: dict[str, Any]
    #: Set by the accept gate and the consent gate from the resume payload.
    accept_votes: dict[str, str]
    reveal_votes: dict[str, str]
    #: Per-user views produced by the outcome node. What a person actually saw.
    views: dict[str, Any]
    #: Human-readable trail, appended by every node. This is what the CLI
    #: prints beside the OTEL trace.
    trail: Annotated[list[str], _append]
    #: Why the encounter ended, for the operator. Never rendered to a user.
    terminal_reason: str
    lockin_id: str


@dataclass
class SparkRuntime:
    """Everything the nodes need, assembled once.

    Passed in rather than imported so that a test can swap the Match Agent for
    a baseline arm, or hand in a ledger it can inspect, without touching the
    graph. It is also what makes the three-arm evaluation possible: the arms
    differ by one field of this object and nothing else.
    """

    client: MCPClient
    trust: TrustAndSafety
    ledger: ConsentLedger
    delivery: EncounterDelivery
    match: MatchPolicy
    continuity: ContinuityAgent
    clock: SimClock
    users: dict[str, User] = field(default_factory=dict)
    #: Encounters per user so far, for the fairness term in the Match Agent.
    encounter_counts: Any = None
    #: Who each user has met recently, for the novelty term.
    recent_partners: dict[str, set[str]] = field(default_factory=dict)
    #: Users who already have today's encounter. One encounter per person per
    #: day is the product, so these are simply not in the pool — the alternative
    #: is selecting someone unavailable and dropping the encounter, which spends
    #: a person's only chance that day on a collision.
    unavailable_today: set[str] = field(default_factory=set)
