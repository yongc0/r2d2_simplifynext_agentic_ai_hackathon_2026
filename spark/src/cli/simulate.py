"""The full simulation — 200 personas, six weeks, one run.

    uv run -m src.cli.simulate --weeks 6
    uv run -m src.cli.simulate --weeks 6 --verbose      # a line per day
    uv run -m src.cli.simulate --write-data             # regenerate data/

This is the recording. It runs the same engine the evaluation runs, prints the
week-by-week shape of the thing, and ends with one encounter's trace and a
side-by-side of week 1 and week 5 for the same lock-in — which is the evidence
for "plans, acts and adapts over time" rather than the assertion of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as Date

from src.cli._console import rule, use_utf8
from src.config import RUNS_DIR, SETTINGS
from src.models import BREAKER, BUDGET, provider_available
from src.sim.engine import SimulationEngine
from src.sim.world import write_all_data
from src.telemetry.metrics import METRICS
from src.telemetry.trace import setup_tracing

DAY_ZERO = Date(2026, 9, 1)


def main(argv: list[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description="Spark, simulated over weeks.")
    parser.add_argument("--weeks", type=int, default=SETTINGS.sim.weeks)
    parser.add_argument("--personas", type=int, default=SETTINGS.sim.personas)
    parser.add_argument("--seed", type=int, default=SETTINGS.sim.seed)
    parser.add_argument("--arm", default="spark", choices=("spark", "random", "similarity"))
    parser.add_argument("--verbose", action="store_true", help="a line per simulated day")
    parser.add_argument(
        "--write-data", action="store_true",
        help="regenerate data/personas.json, data/adversarial.json and data/cells.json",
    )
    parser.add_argument("--trace-file", action="store_true",
                        help="also write every span to runs/trace.jsonl")
    args = parser.parse_args(argv)

    setup_tracing(to_file=args.trace_file)
    METRICS.reset()
    BUDGET.reset(SETTINGS.sim.llm_call_budget)
    BREAKER.reset()

    if args.write_data:
        written = write_all_data(args.seed, args.personas, DAY_ZERO, args.weeks * 7)
        print("Regenerated:")
        for name, path in written.items():
            print(f"  {name:<12} {path}")
        print()

    print(rule("SPARK — SIMULATION"))
    print(
        f"{args.personas} personas · {args.weeks} weeks · seed {args.seed} · "
        f"arm: {args.arm}"
    )
    print(f"provider: {SETTINGS.model.provider}", end="")
    if provider_available():
        print(
            f" (reasoning: {SETTINGS.model.model_id('reasoning')}, "
            f"budget {BUDGET.limit} calls)"
        )
    else:
        print(" — every judgement call uses the deterministic policy.")
        print(
            "          Set GROQ_API_KEY in spark/.env to run the model path.\n"
            "          Nothing below is presented as a model result."
        )
    print(
        f"rules: {SETTINGS.rules.call_seconds}s calls · "
        f"{SETTINGS.rules.max_lockins} lock-in slots · "
        f"{SETTINGS.rules.rematch_cooldown_days}-day rematch cooldown"
    )
    print()

    engine = SimulationEngine(
        arm=args.arm, seed=args.seed, personas=args.personas,
        weeks=args.weeks, day_zero=DAY_ZERO, verbose=args.verbose,
    )
    result = engine.run()
    totals = result.totals

    # -- what happened -------------------------------------------------
    print(rule("WHAT HAPPENED"))
    rows = [
        ("encounters offered", totals.encounters_offered, ""),
        ("accepted by both", totals.encounters_accepted,
         _pct(totals.encounters_accepted, totals.encounters_offered)),
        ("calls completed", totals.calls_completed, ""),
        ("mutual connections", totals.mutual_connects,
         _pct(totals.mutual_connects, totals.calls_completed)),
        ("lock-ins opened", totals.lockins_opened, ""),
        ("met in person by day 14", totals.met_in_person_by_day_14,
         _pct(totals.met_in_person_by_day_14, totals.lockins_opened)),
        ("lock-ins alive at week 4", totals.lockins_active_at_week_4,
         _pct(totals.lockins_active_at_week_4, totals.lockins_opened)),
        ("lock-ins released gracefully", totals.lockins_released, ""),
    ]
    for label, value, share in rows:
        print(f"  {label:<32}{value:>7}  {share}")

    # -- the metrics ---------------------------------------------------
    snapshot = result.metrics
    print(rule("METRICS"))
    for key, target in (
        ("schema_validation", ">= 98%"),
        ("tool_calls", ">= 95%"),
        ("task_completion", ">= 90%"),
        ("answer_fidelity", ">= 95%"),
        ("anonymity_leakage", "zero"),
    ):
        entry = snapshot[key]
        rate = "n/a" if entry["rate"] is None else f"{entry['rate']:.2%}"
        print(f"  {entry['label']:<32}{rate:>9}  (n={entry['total']:<6}) target {target}")
    loop = snapshot["loop"]
    print(
        f"  {'loop discipline (at cap)':<32}"
        f"{(loop['cap_hit_rate'] or 0):>8.2%}  (n={loop['runs']:<6}) target < 2%"
    )
    print(f"  {'encounter distribution (Gini)':<32}{snapshot['encounter_gini']:>9.3f}")
    print(f"  {'users who got an encounter':<32}{snapshot['users_with_encounters']:>9}")
    if snapshot["llm_calls"]["attempted"]:
        print(
            f"  {'model calls':<32}"
            f"{snapshot['llm_calls']['succeeded']:>9}  of "
            f"{snapshot['llm_calls']['attempted']} attempted, "
            f"${snapshot['total_cost_usd']:.4f}"
        )

    # -- adaptation over time -----------------------------------------
    print(rule("DOES IT ADAPT OVER TIME?"))
    if len(result.continuity_examples) >= 2:
        print("  The same lock-in, four weeks apart:\n")
        for example in result.continuity_examples:
            print(f"    {example}")
        print(
            "\n  Week 1 has one note and sends a brief. By week 5 the agent has a\n"
            "  history, a learned pace, and something specific to re-enter on."
        )
    elif result.continuity_examples:
        print("  Only a week-1 example was captured — run more weeks to see the")
        print("  contrast:  uv run -m src.cli.simulate --weeks 6")
        for example in result.continuity_examples:
            print(f"    {example}")
    else:
        print("  No lock-in in this run survived long enough to show the contrast.")
        print("  That is a real outcome, not a missing feature.")

    # -- what it could not do -----------------------------------------
    print(rule("WHAT THIS RUN COULD NOT DO"))
    if result.notes:
        for note in result.notes:
            print(f"  · {note}")
    else:
        print("  · Nothing was skipped, capped or dropped.")

    # -- the trace -----------------------------------------------------
    if result.demo_trace:
        print(rule("ONE ENCOUNTER, TRACED"))
        print(result.demo_trace)

    out = RUNS_DIR / "simulation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "arm": result.arm,
                "provider": result.provider,
                "seed": result.seed,
                "weeks": result.weeks,
                "personas": result.personas,
                "totals": totals.as_dict(),
                "metrics": snapshot,
                "continuity_examples": result.continuity_examples,
                "notes": result.notes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out}")
    if args.trace_file:
        print(f"Wrote {SETTINGS.trace_file}")
    print("\nFor the three-arm comparison:  uv run -m eval.run_arms && uv run -m eval.report")
    return 0


def _pct(numerator: int, denominator: int) -> str:
    return "" if denominator == 0 else f"({numerator / denominator:.1%})"


if __name__ == "__main__":
    sys.exit(main())
