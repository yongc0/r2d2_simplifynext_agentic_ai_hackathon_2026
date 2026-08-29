"""One encounter, end to end, with everything shown.

    uv run -m src.cli.encounter --seed 42
    uv run -m src.cli.encounter --seed 42 --decline    # the silent path
    uv run -m src.cli.encounter --graph                # print the supervisor graph

This is the demo. It walks a single encounter from an overlap pool to a lock-in
and prints, at each step: what each person actually saw, what the graph did,
and the OpenTelemetry trace underneath it.

Two things are worth watching for.

**Nothing on either card is a name, a place or a distance.** The card is built
from `AnonymousPeer`, which has no field for any of them.

**`--decline` produces the same close-out, byte for byte, as a timeout.** Run
it both ways and diff the output: that is INVARIANT 2, visible rather than
asserted.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date as Date

from langgraph.types import Command

from src import agui
from src.agents.continuity import ContinuityAgent
from src.agents.delivery import EncounterDelivery
from src.agents.match import MatchAgent
from src.agents.onboarding import OnboardingAgent
from src.cli._console import rule, use_utf8
from src.clock import SimClock
from src.config import SETTINGS
from src.graph.state import SparkRuntime
from src.graph.supervisor import build_encounter_graph, pending_gate, render_graph_ascii
from src.ids import encounter_id
from src.mcp.registry import MCPClient, catalogue
from src.mcp.services import WORLD
from src.safety.consent import ConsentLedger
from src.safety.trust import TrustAndSafety
from src.schemas.core import Encounter
from src.schemas.views import EncounterCard
from src.sim.world import SimWorldBuilder
from src.telemetry.metrics import METRICS
from src.telemetry.trace import TRACES, setup_tracing, span

DAY_ZERO = Date(2026, 9, 1)


#: The personas behind the simulated users, kept so the onboarding step can
#: replay what one of them "typed". Nothing in src/agents/ may read this.
_PERSONAS: list = []


def _build_runtime(seed: int, personas: int, day_offset: int) -> tuple[SparkRuntime, SimClock]:
    builder = SimWorldBuilder(seed=seed, persona_count=personas)
    builder.build(day_zero=DAY_ZERO, days=day_offset + 14)
    _PERSONAS.clear()
    _PERSONAS.extend(builder.personas)
    client = MCPClient()
    trust = TrustAndSafety()
    ledger = ConsentLedger()
    clock = SimClock(DAY_ZERO)
    clock.advance(day_offset)
    runtime = SparkRuntime(
        client=client,
        trust=trust,
        ledger=ledger,
        delivery=EncounterDelivery(client=client, ledger=ledger),
        match=MatchAgent(client=client, trust=trust, max_lockins=SETTINGS.rules.max_lockins),
        continuity=ContinuityAgent(client=client),
        clock=clock,
        users=dict(WORLD.users),
        encounter_counts=Counter(),
    )
    return runtime, clock


def _pick_starter(runtime: SparkRuntime, clock: SimClock) -> str:
    """The first user who actually has an eligible candidate today.

    A non-empty overlap pool is not enough — intent, language, availability and
    cooldown all still have to pass, and on any given day most people's pools
    do not survive them. That is a real property of the product (a quiet day is
    a normal day), but it is a poor default for a demo, so this looks for a day
    that goes somewhere.

    The dry-run selections are discarded afterwards: `main` resets the metrics
    and the trace so that what is printed is one encounter, not sixty.
    """
    for user_id in sorted(WORLD.users):
        result = runtime.client.try_call(
            "spark-overlap", "overlap_pool", default={"candidates": []},
            user_id=user_id, day=clock.current.isoformat(),
        ) or {"candidates": []}
        pool = [
            runtime.users[c["candidate_id"]]
            for c in result["candidates"]
            if c["candidate_id"] in runtime.users
        ]
        if pool and runtime.match.select(runtime.users[user_id], pool, clock.current):
            return user_id
    raise SystemExit(
        "Nobody has an eligible candidate on this day — every overlap failed the "
        "intent, language, availability or cooldown rules. Try a different "
        "--seed, a later --day, or more --personas."
    )



def _show_onboarding(runtime: SparkRuntime, user_id: str) -> None:
    """Step one of the MVP chain: what someone typed -> a validated Profile.

    Two things are demonstrated, and the second is the one that matters.

    The extraction turns prose into structure. And the transcript contains both
    an appearance aside and a sentence that *sounds* like an intent without
    naming one — neither of which may reach the profile. §13.1: intent is never
    inferred from tone.
    """
    from src.sim.transcripts import silent_on_intent_transcript, transcript_for

    persona = next(
        (p for p in _PERSONAS if p.id == user_id), None
    )
    if persona is None:
        return

    agent = OnboardingAgent(trust=runtime.trust)
    print(rule("ONBOARDING — conversational intake, not a form", "-"))

    transcript = transcript_for(persona)
    print(f'\n  what they typed:\n    "{transcript}"')
    extraction = agent.extract(user_id, transcript)
    _show("extracted:", extraction.model_dump(mode="json"))
    if extraction.intents:
        profile, scope = agent.to_profile(user_id, extraction)
        print(
            "\n  -> Profile validated. Intents: "
            f"{', '.join(i.value for i in profile.intents)}"
        )
        print(f"  -> ConsentScope: {', '.join(scope.matchable_fields)}")
    print(
        "\n  Note what did NOT survive: any mention of appearance. There is no\n"
        "  field on Profile for height or a photograph, by design."
    )

    # The case §13.1 exists for.
    print("\n  And a transcript that never names an intent:")
    silent = silent_on_intent_transcript()
    print(f'    "{silent}"')
    quiet = agent.extract("u-demo", silent)
    print(f"\n  -> intents: {quiet.intents or '[] (nothing was inferred)'}")
    print(f"  -> unresolved: {quiet.unresolved}")
    print(f'  -> the agent asks: "{agent.follow_up_question(quiet)}"')


def _show(title: str, payload) -> None:
    print(f"\n  {title}")
    print("  " + json.dumps(payload, indent=2, default=str).replace("\n", "\n  "))


def main(argv: list[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description="One encounter, verbose, with its trace.")
    parser.add_argument("--seed", type=int, default=SETTINGS.sim.seed)
    parser.add_argument("--personas", type=int, default=60,
                        help="a smaller world than the full simulation; it is one encounter")
    parser.add_argument("--day", type=int, default=2, help="days after 2026-09-01")
    parser.add_argument(
        "--decline", action="store_true",
        help="the second party declines the reveal — shows the silent close-out",
    )
    parser.add_argument(
        "--timeout", action="store_true",
        help="the second party never answers — must be indistinguishable from --decline",
    )
    parser.add_argument("--graph", action="store_true", help="print the supervisor graph and exit")
    parser.add_argument("--tools", action="store_true", help="print the MCP tool catalogue and exit")
    parser.add_argument(
        "--agui", action="store_true",
        help="also print the AG-UI render directives the agent emits",
    )
    parser.add_argument(
        "--skip-onboarding", action="store_true",
        help="start at the overlap pool instead of at intake",
    )
    args = parser.parse_args(argv)

    setup_tracing()
    runtime, clock = _build_runtime(args.seed, args.personas, args.day)

    if args.graph:
        print(rule("THE SUPERVISOR GRAPH"))
        print(render_graph_ascii(runtime))
        return 0
    if args.tools:
        print(rule("MCP TOOL CATALOGUE — six servers"))
        for entry in catalogue():
            print(f"\n  {entry['server']} · {entry['tool']}")
            print(f"    {entry['description']}")
        return 0

    starter = _pick_starter(runtime, clock)
    # The search above ran the Match Agent over several users. Discard that, so
    # the trace and the metrics printed at the end describe ONE encounter.
    METRICS.reset()
    TRACES.reset()
    runtime.trust = TrustAndSafety()          # the dry runs noted matches; undo them
    runtime.match.trust = runtime.trust

    encounter = Encounter(
        id=encounter_id(clock.current.isoformat(), starter, "demo"),
        match_id=f"match-{clock.current.isoformat()}-{starter}",
        day=clock.current,
        user_a=starter,
        user_b=f"{starter}-tbd",
    )
    config = {"configurable": {"thread_id": encounter.id}}
    app = build_encounter_graph(runtime)

    print(rule("SPARK — ONE ENCOUNTER"))
    print(
        f"seed={args.seed} · day={clock.current} (week {clock.week_index}) · "
        f"provider={SETTINGS.model.provider}"
    )
    print(f"starting user: {starter} (handle: {WORLD.users[starter].handle})")

    if not args.skip_onboarding:
        _show_onboarding(runtime, starter)

    # ONE span around the whole encounter, so the three graph invocations
    # below land in a single trace (§11.6: one trace per encounter).
    with span("encounter", encounter_id=encounter.id, user_id=starter):
        return _walk(app, config, encounter, runtime, clock, starter, args)


def _walk(app, config, encounter, runtime, clock, starter, args) -> int:
    # --- to the first gate --------------------------------------------
    result = app.invoke(
        {
            "encounter": encounter,
            "users": {starter: WORLD.users[starter]},
            "day": clock.current,
            "trail": [],
        },
        config,
    )
    encounter = result["encounter"]
    if not pending_gate(result):
        print("\nNo eligible candidate crossed this user's path today — a quiet day.")
        print("That is a normal outcome, not a failure.")
        for entry in result.get("trail", []):
            print(f"  {entry}")
        return 0

    peer = encounter.user_b
    print(rule("GATE 1 — will you take an anonymous three-minute call?", "-"))
    print("  The graph is HALTED here. It is checkpointed, and there is no code")
    print("  path to the call without a resume carrying both answers.")
    for viewer in (starter, peer):
        _show(f"what {viewer} sees:", result["views"]["cards"][viewer])
    if args.agui:
        print("\n  AG-UI — what the agent tells the client to draw:")
        for viewer in (starter, peer):
            directive = agui.encounter_card(
                EncounterCard.model_validate(result["views"]["cards"][viewer]), viewer
            )
            print(f"    {directive.component} -> {directive.audience}, "
                  f"actions={directive.actions}, blocking={directive.blocking}")
    print(
        "\n  Note what is absent from both cards: no name, no photo, no number,\n"
        "  no place, no distance. `AnonymousPeer` has no field for any of them."
    )

    # --- through the call ---------------------------------------------
    result = app.invoke(Command(resume={starter: "yes", peer: "yes"}), config)
    encounter = result["encounter"]
    print(rule("THE CALL", "-"))
    print(f"  {encounter.call_duration_s} seconds, stopped by the time limit.")
    print("  The duration is not a parameter of the bridge — INVARIANT 4.")

    # --- the reveal gate ----------------------------------------------
    print(rule("GATE 2 — may we swap names?", "-"))
    print("  Asked privately of each person, in identical words. Neither is told")
    print("  whether the other has answered, is answering, or already has.")
    prompt = runtime.delivery.consent_prompt(encounter, encounter.call_ended)
    _show("the question, to both:", prompt.model_dump(mode="json"))

    if args.timeout:
        answers = {starter: "yes"}                   # the peer never replies
        label = "the other person never answered"
    elif args.decline:
        answers = {starter: "yes", peer: "no"}
        label = "the other person declined"
    else:
        answers = {starter: "yes", peer: "yes"}
        label = "both said yes"
    print(f"\n  This run: {label}.")

    result = app.invoke(Command(resume=answers), config)
    encounter = result["encounter"]

    print(rule("THE OUTCOME", "-"))
    for viewer in (starter, peer):
        _show(f"what {viewer} sees:", result["views"]["outcome"][viewer])
    if args.decline or args.timeout:
        print(
            "\n  Run this again with the other flag and diff the two outputs.\n"
            "  They are identical, including the timestamp. That is INVARIANT 2:\n"
            "  a decline and a silence must not be distinguishable."
        )

    # --- the trail and the trace --------------------------------------
    print(rule("STATE MACHINE"))
    for entry in result.get("trail", []):
        print(f"  {entry}")
    print(f"\n  final state: {encounter.state.value}")

    print(rule("OPENTELEMETRY TRACE"))
    print(TRACES.tree(encounter.trace_id))

    print(rule("METRICS FOR THIS ENCOUNTER"))
    snapshot = METRICS.snapshot()
    for key in (
        "schema_validation", "tool_calls", "task_completion", "anonymity_leakage",
    ):
        entry = snapshot[key]
        rate = "n/a" if entry["rate"] is None else f"{entry['rate']:.1%}"
        print(f"  {entry['label']:<32} {rate:>8}  (n={entry['total']})")
    print(f"  {'loop iterations / cap':<32} "
          f"{snapshot['loop']['mean_iterations'] or 0:>8.2f}  "
          f"(cap {snapshot['loop']['cap']}, hit {snapshot['loop']['cap_hit_rate'] or 0:.1%})")
    if snapshot["llm_calls"]["attempted"]:
        print(f"  {'model calls':<32} {snapshot['llm_calls']['succeeded']:>8}"
              f"  of {snapshot['llm_calls']['attempted']} attempted")
    else:
        print(f"  {'model calls':<32} {'none':>8}  (deterministic policy)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
