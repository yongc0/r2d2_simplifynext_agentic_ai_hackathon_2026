"""Run the three arms and write the results.

    uv run -m eval.run_arms
    uv run -m eval.run_arms --seeds 3 --weeks 6 --personas 200

Each arm runs the *same* simulated world, the same personas, the same latent
affinities and the same eligibility rules. The only difference is which
candidate gets picked from the eligible pool.

Repeated seeds matter more than they look. One six-week run over 200 personas
produces a few dozen mutual connections, and a few dozen of anything has a wide
confidence interval. `--seeds 3` runs three independent worlds and pools them,
which is the difference between a number and a result.

Output: `runs/arms.json`, read by `eval/report.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.cli._console import use_utf8
from src.config import RUNS_DIR, SETTINGS
from src.models import BREAKER, BUDGET
from src.sim.engine import SimulationEngine
from src.telemetry.metrics import METRICS
from src.telemetry.trace import TRACES, setup_tracing

ARMS = ("spark", "random", "similarity")


def run_arm(arm: str, seed: int, weeks: int, personas: int) -> dict:
    """One arm, one seed. Metrics are reset first so each arm's numbers are its
    own — a shared registry would let the first arm's tool calls flatter the
    third arm's success rate."""
    METRICS.reset()
    TRACES.reset()
    BUDGET.reset(SETTINGS.sim.llm_call_budget)
    BREAKER.reset()

    engine = SimulationEngine(arm=arm, seed=seed, personas=personas, weeks=weeks)
    result = engine.run()
    return {
        "arm": arm,
        "seed": seed,
        "provider": result.provider,
        "weeks": weeks,
        "personas": personas,
        "totals": result.totals.as_dict(),
        "metrics": result.metrics,
        "notes": result.notes,
        "continuity_examples": result.continuity_examples,
        "lockin_detail": _lockin_detail(engine),
    }


def _lockin_detail(engine: SimulationEngine) -> dict:
    """Per-lock-in facts the report needs, without keeping the objects."""
    return {
        "opened": len(engine.lockins),
        "contacts_total": sum(l.contacts for l in engine.lockins.values()),
        "met_in_person": sum(
            1 for l in engine.lockins.values() if l.met_in_person_on is not None
        ),
        "mean_pace_days": (
            round(
                sum(l.pace_pref_days for l in engine.lockins.values())
                / len(engine.lockins),
                2,
            )
            if engine.lockins
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Spark vs random assignment vs naive interest similarity.",
    )
    parser.add_argument("--seeds", type=int, default=3, help="independent worlds to run")
    parser.add_argument("--weeks", type=int, default=SETTINGS.sim.weeks)
    parser.add_argument("--personas", type=int, default=SETTINGS.sim.personas)
    parser.add_argument(
        "--base-seed", type=int, default=SETTINGS.sim.seed,
        help="first seed; subsequent worlds are base-seed + n",
    )
    parser.add_argument(
        "--arms", nargs="+", default=list(ARMS), choices=ARMS,
        help="which arms to run (all three by default)",
    )
    parser.add_argument("--out", default=str(RUNS_DIR / "arms.json"))
    args = parser.parse_args(argv)
    use_utf8()

    setup_tracing()
    print(
        f"Running {len(args.arms)} arm(s) x {args.seeds} seed(s): "
        f"{args.personas} personas, {args.weeks} weeks, "
        f"provider={SETTINGS.model.provider}"
    )
    if SETTINGS.model.provider == "deterministic":
        print(
            "  No model provider configured, so every judgement call uses the\n"
            "  deterministic policy. The report labels the run accordingly.\n"
            "  Set GROQ_API_KEY in spark/.env for the model path."
        )

    runs: list[dict] = []
    for arm in args.arms:
        for offset in range(args.seeds):
            seed = args.base_seed + offset
            print(f"  {arm:<11} seed={seed} ... ", end="", flush=True)
            run = run_arm(arm, seed, args.weeks, args.personas)
            totals = run["totals"]
            print(
                f"{totals['encounters_offered']:>5} offered, "
                f"{totals['mutual_connects']:>3} connections"
            )
            runs.append(run)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": SETTINGS.model.provider,
        "model_reasoning": SETTINGS.model.model_id("reasoning"),
        "model_fast": SETTINGS.model.model_id("fast"),
        "seeds": args.seeds,
        "base_seed": args.base_seed,
        "weeks": args.weeks,
        "personas": args.personas,
        "rules": asdict(SETTINGS.rules),
        "runs": runs,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    print("Now run:  uv run -m eval.report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
