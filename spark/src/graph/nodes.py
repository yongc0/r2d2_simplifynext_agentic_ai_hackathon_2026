"""One node per transition in the state machine (docs/ARCHITECTURE.md §14).

Read this file beside the state-machine diagram; they are the same picture.

    PROFILED -> POOLED -> SELECTED -> NOTIFIED -> PENDING_ACCEPT -> CONNECTED
                                          |               |
                              (decline/timeout)           v
                                          v           CALL_ENDED
                                      ABANDONED           |
                                                          v
                                                  PENDING_CONSENT
                                                     |         |
                                            (mutual) |         | (not mutual)
                                                     v         v
                                                REVEALED    CLOSED
                                                     |
                                                     v
                                                LOCKED_IN -> RELEASED

**The two gates are `interrupt()` calls.** Not a screen, not a flag, not a
callback — the graph halts, its state is checkpointed, and there is no code
path that continues without a resume carrying both answers. That is the whole
of §11.4, and `tests/test_graph.py` kills the process between the halt and the
resume to prove it.

A note on interrupts and idempotency: when a node containing `interrupt()` is
resumed, LangGraph re-runs the node from the top. So in both gate nodes,
*nothing happens before the interrupt* — the call is the first statement, and
every side effect follows it.
"""

from __future__ import annotations

from datetime import timedelta

from langgraph.types import interrupt

from src.graph.state import EncounterGraphState, SparkRuntime
from src.ids import lockin_id as make_lockin_id
from src.mcp.registry import ToolError
from src.schemas.core import ConsentDecision, EncounterState, TimeBucket
from src.telemetry.metrics import METRICS
from src.telemetry.trace import current_trace_id, span


def _vote(raw: dict[str, str] | None, user_id: str) -> ConsentDecision:
    """Read one answer out of a resume payload.

    A missing answer is a `TIMEOUT`, and a timeout is treated exactly as a
    decline from here on. Collapsing them this early is what stops "they never
    answered" and "they said no" from being distinguishable downstream.
    """
    if not raw:
        return ConsentDecision.TIMEOUT
    value = str(raw.get(user_id, "")).strip().lower()
    if value in ("yes", "y", "true", "accept"):
        return ConsentDecision.YES
    if value in ("no", "n", "false", "decline"):
        return ConsentDecision.NO
    return ConsentDecision.TIMEOUT


# ---------------------------------------------------------------------------
# PROFILED -> POOLED
# ---------------------------------------------------------------------------


def make_pool_node(runtime: SparkRuntime):
    """Ask `spark-overlap` who crossed this user's path on this day."""

    def pool_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        day = state["day"]
        with span("node.pool", encounter_id=encounter.id, day=day.isoformat()) as s:
            encounter.trace_id = current_trace_id()
            result = runtime.client.try_call(
                "spark-overlap",
                "overlap_pool",
                default={"candidates": []},
                user_id=encounter.user_a,
                day=day.isoformat(),
            ) or {"candidates": []}
            pool = [c["candidate_id"] for c in result["candidates"]]
            encounter.transition_to(EncounterState.POOLED)
            s.set_attribute("pool_size", len(pool))
            return {
                "encounter": encounter,
                "pool": pool,
                "trail": [f"POOLED — {len(pool)} paths crossed today"],
            }

    return pool_node


# ---------------------------------------------------------------------------
# POOLED -> SELECTED (or ABANDONED)
# ---------------------------------------------------------------------------


def make_select_node(runtime: SparkRuntime):
    """The Match Agent picks one, or nobody is eligible and the day is quiet."""

    def select_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        day = state["day"]
        user = state["users"][encounter.user_a]
        with span("node.select", encounter_id=encounter.id) as s:
            pool_users = [
                runtime.users[uid]
                for uid in state.get("pool", [])
                if uid in runtime.users and uid not in runtime.unavailable_today
            ]
            decision = runtime.match.select(
                user,
                pool_users,
                day,
                recent_partners=runtime.recent_partners.get(user.id, set()),
                encounter_counts=runtime.encounter_counts,
            )
            if decision is None:
                encounter.transition_to(EncounterState.ABANDONED)
                s.set_attribute("outcome", "no candidate")
                # Not a task failure: nobody eligible crossed their path today.
                # Counting it as one would make the metric a measure of the
                # city rather than of the system.
                return {
                    "encounter": encounter,
                    "terminal_reason": "no eligible candidate in today's overlap pool",
                    "trail": ["ABANDONED — nobody eligible crossed your path today"],
                }

            encounter.user_b = decision.candidate_id
            encounter.transition_to(EncounterState.SELECTED)
            runtime.trust.note_match(encounter.user_a, encounter.user_b, day)
            s.set_attribute("selected", decision.candidate_id)
            return {
                "encounter": encounter,
                "decision": decision.model_dump(mode="json"),
                "users": {
                    **state["users"],
                    decision.candidate_id: runtime.users[decision.candidate_id],
                },
                "trail": [
                    f"SELECTED — {decision.candidate_id} "
                    f"(confidence {decision.confidence:.2f})"
                ],
            }

    return select_node


# ---------------------------------------------------------------------------
# SELECTED -> NOTIFIED -> PENDING_ACCEPT
# ---------------------------------------------------------------------------


def make_notify_node(runtime: SparkRuntime):
    """Build one anonymous card per person and offer the call."""

    def notify_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        users = state["users"]
        decision = state.get("decision", {})
        with span("node.notify", encounter_id=encounter.id):
            notified_at = runtime.clock.at(18, 0)
            shared_bucket = _shared_bucket(runtime, encounter.user_a, encounter.user_b)
            cards = {}
            for viewer_id in encounter.participants():
                peer_id = encounter.other(viewer_id)
                shared = sorted(
                    set(users[viewer_id].profile.interests)
                    & set(users[peer_id].profile.interests)
                )
                cards[viewer_id] = runtime.delivery.build_card(
                    encounter=encounter,
                    viewer=users[viewer_id],
                    peer=users[peer_id],
                    # Both people get a rationale. The Match Agent wrote one for
                    # the user it selected for; the other party gets the neutral
                    # one, because a rationale written *about* someone is a
                    # description of them.
                    rationale=(
                        decision.get("rationale", "Your paths crossed today.")
                        if viewer_id == encounter.user_a
                        else "Your paths crossed today."
                    ),
                    shared_interests=shared,
                    shared_bucket=shared_bucket,
                    notified_at=notified_at,
                ).model_dump(mode="json")

            encounter.transition_to(EncounterState.NOTIFIED)
            encounter.transition_to(EncounterState.PENDING_ACCEPT)
            return {
                "encounter": encounter,
                "views": {**state.get("views", {}), "cards": cards},
                "trail": ["NOTIFIED — both offered an anonymous three-minute call"],
            }

    return notify_node


def _shared_bucket(runtime: SparkRuntime, user_a: str, user_b: str) -> TimeBucket | None:
    result = runtime.client.try_call(
        "spark-calendar",
        "shared_availability",
        default={"shared_buckets": []},
        user_a=user_a,
        user_b=user_b,
    ) or {"shared_buckets": []}
    buckets = result["shared_buckets"]
    return TimeBucket(buckets[0]) if buckets else None


# ---------------------------------------------------------------------------
# GATE 1 — PENDING_ACCEPT. interrupt().
# ---------------------------------------------------------------------------


def make_accept_gate(runtime: SparkRuntime):
    """The graph halts until both people have answered the notification.

    There is no timeout branch inside the node, and that is deliberate: a
    timeout is a *resume* carrying no answer for someone, which `_vote` reads as
    `TIMEOUT`. The caller decides when the window has closed; the graph simply
    waits, checkpointed, for as long as that takes.
    """

    def accept_gate(state: EncounterGraphState) -> dict:
        # FIRST STATEMENT. On resume this node re-runs from here, so nothing
        # above it may have side effects — there is nothing above it.
        votes = interrupt(
            {
                "gate": "accept",
                "encounter_id": state["encounter"].id,
                "question": "Would you like to take an anonymous three-minute call?",
                "participants": list(state["encounter"].participants()),
            }
        )
        encounter = state["encounter"]
        with span("node.accept_gate", encounter_id=encounter.id) as s:
            at = runtime.clock.at(18, 30)
            for user_id in encounter.participants():
                runtime.delivery.record_accept(encounter, user_id, _vote(votes, user_id), at)
            both = runtime.delivery.both_accepted(encounter)
            s.set_attribute("both_accepted", both)
            if not both:
                encounter.transition_to(EncounterState.ABANDONED)
                # The reason is recorded for the operator only. Neither party
                # is told anything at all — INVARIANT 2.
                return {
                    "encounter": encounter,
                    "accept_votes": dict(votes or {}),
                    "terminal_reason": "not accepted by both parties",
                    "trail": ["ABANDONED — the call was not taken up on both sides"],
                }
            encounter.transition_to(EncounterState.CONNECTED)
            return {
                "encounter": encounter,
                "accept_votes": dict(votes or {}),
                "trail": ["CONNECTED — both accepted"],
            }

    return accept_gate


# ---------------------------------------------------------------------------
# CONNECTED -> CALL_ENDED
# ---------------------------------------------------------------------------


def make_call_node(runtime: SparkRuntime):
    """Three minutes, and not a second more. INVARIANT 4."""

    def call_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        with span("node.call", encounter_id=encounter.id) as s:
            started = runtime.clock.at(19, 0)
            try:
                ended, duration = runtime.delivery.connect(encounter, started)
            except ToolError as exc:
                # The bridge failed. The encounter is abandoned and BOTH people
                # see the same nothing they would have seen if the other had
                # declined — an outage must not be distinguishable from a
                # decline either.
                encounter.transition_to(EncounterState.ABANDONED)
                s.set_attribute("outcome", "bridge failure")
                METRICS.record_task_completion(
                    reached_gate=False,
                    detail=(
                        f"encounter {encounter.id} did not reach the consent gate: "
                        f"{exc.detail} Neither party was told the failure was ours."
                    ),
                )
                return {
                    "encounter": encounter,
                    "terminal_reason": f"voice bridge unavailable: {exc.detail}",
                    "trail": ["ABANDONED — the call could not be connected"],
                }
            encounter.call_started = started
            encounter.call_ended = ended
            encounter.call_duration_s = duration
            encounter.transition_to(EncounterState.CALL_ENDED)
            return {
                "encounter": encounter,
                "trail": [f"CALL_ENDED — {duration}s, stopped by the time limit"],
            }

    return call_node


# ---------------------------------------------------------------------------
# GATE 2 — PENDING_CONSENT. interrupt(). The one that matters.
# ---------------------------------------------------------------------------


def make_consent_gate(runtime: SparkRuntime):
    """The graph halts until both have privately answered "may we swap names".

    This is the gate INVARIANT 1 is about. Below it, `reveal_or_close` is the
    only path to an identity, and it needs a mutual yes.
    """

    def consent_gate(state: EncounterGraphState) -> dict:
        # FIRST STATEMENT, for the same reason as the accept gate.
        votes = interrupt(
            {
                "gate": "reveal",
                "encounter_id": state["encounter"].id,
                "question": (
                    "Would you like to swap names and keep talking? "
                    "We will only tell either of you if you both say yes."
                ),
                "participants": list(state["encounter"].participants()),
            }
        )
        encounter = state["encounter"]
        with span("node.consent_gate", encounter_id=encounter.id) as s:
            encounter.transition_to(EncounterState.PENDING_CONSENT)
            at = (encounter.call_ended or runtime.clock.at(19, 3)) + timedelta(minutes=5)
            for user_id in encounter.participants():
                runtime.delivery.record_reveal_decision(
                    encounter, user_id, _vote(votes, user_id), at
                )
            # Reaching this point IS task completion (§17, metric 5): the system
            # carried the job to the human gate with no manual intervention.
            # Whether the humans said yes is their business, not the system's
            # score.
            METRICS.record_task_completion(reached_gate=True)
            s.set_attribute("reached_gate", True)
            return {
                "encounter": encounter,
                "reveal_votes": dict(votes or {}),
                "trail": ["PENDING_CONSENT — both asked privately"],
            }

    return consent_gate


# ---------------------------------------------------------------------------
# PENDING_CONSENT -> REVEALED | CLOSED
# ---------------------------------------------------------------------------


def make_outcome_node(runtime: SparkRuntime):
    """Mutual yes, or a close-out that says nothing."""

    def outcome_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        users = state["users"]
        with span("node.outcome", encounter_id=encounter.id) as s:
            lockin = make_lockin_id(encounter.user_a, encounter.user_b)
            at = (encounter.call_ended or runtime.clock.at(19, 3)) + timedelta(minutes=10)
            views = runtime.delivery.reveal_or_close(encounter, users, lockin, at)
            revealed = all(
                type(v).__name__ == "RevealView" for v in views.values()
            )
            s.set_attribute("revealed", revealed)
            if revealed:
                encounter.revealed = True
                encounter.transition_to(EncounterState.REVEALED)
                METRICS.record_mutual_connection()
                return {
                    "encounter": encounter,
                    "lockin_id": lockin,
                    "views": {
                        **state.get("views", {}),
                        "outcome": {k: v.model_dump(mode="json") for k, v in views.items()},
                    },
                    "trail": ["REVEALED — both said yes"],
                }
            encounter.transition_to(EncounterState.CLOSED)
            return {
                "encounter": encounter,
                "terminal_reason": "no mutual yes at the reveal stage",
                "views": {
                    **state.get("views", {}),
                    "outcome": {k: v.model_dump(mode="json") for k, v in views.items()},
                },
                "trail": ["CLOSED — nothing was shared, in either direction"],
            }

    return outcome_node


# ---------------------------------------------------------------------------
# REVEALED -> LOCKED_IN
# ---------------------------------------------------------------------------


def make_lockin_node(runtime: SparkRuntime):
    """Open the lock-in and write each person their first note.

    This is where a single encounter becomes the thing that lasts weeks, and
    where the Continuity Agent takes over.
    """

    def lockin_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        with span("node.lockin", encounter_id=encounter.id):
            encounter.transition_to(EncounterState.LOCKED_IN)
            return {
                "encounter": encounter,
                "trail": [f"LOCKED_IN — {state.get('lockin_id', '')}"],
            }

    return lockin_node


# ---------------------------------------------------------------------------
# LOCKED_IN -> RELEASED
# ---------------------------------------------------------------------------


def make_release_node(runtime: SparkRuntime):
    """The graceful end, weeks later. A slot is freed and nobody is told off."""

    def release_node(state: EncounterGraphState) -> dict:
        encounter = state["encounter"]
        with span("node.release", encounter_id=encounter.id):
            encounter.transition_to(EncounterState.RELEASED)
            return {
                "encounter": encounter,
                "trail": ["RELEASED — the slot is free again"],
            }

    return release_node


__all__ = [
    "make_accept_gate",
    "make_call_node",
    "make_consent_gate",
    "make_lockin_node",
    "make_notify_node",
    "make_outcome_node",
    "make_pool_node",
    "make_release_node",
    "make_select_node",
]
