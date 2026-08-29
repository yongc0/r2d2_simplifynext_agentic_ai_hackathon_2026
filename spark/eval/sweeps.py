"""Parameter sweeps for the numbers CLAUDE.md lists as guesses.

    uv run -m eval.sweeps --cooldown 0 7 14 30
    uv run -m eval.sweeps --lockins 3 5 8

CLAUDE.md's open questions 1 and 2 are explicitly guesses:

    1. Cooldown before two users can be re-matched. Currently a guess.
    2. Lock-in ceiling of 5 — chosen for attention scarcity, not measured.

This script does not answer them — a simulation cannot tell you what people
want. What it does is show what each value *costs*, which turns "30 days felt
right" into "30 days costs us this much encounter supply, and here is the
number". That is the evidence a product decision should be argued over.

The defaults in `src/config.py` are deliberately left as specified. Changing a
product parameter because a simulation of our own design preferred it would be
tuning the evaluation, which is exactly what we are not doing.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from src.cli._console import use_utf8
from src.config import RUNS_DIR, SETTINGS
from src.telemetry.metrics import METRICS
from src.telemetry.trace import TRACES


def _run(weeks: int, personas: int, seed: int) -> dict:
    # Imported here so each sweep step picks up the patched settings.
    from src.sim.engine import SimulationEngine

    METRICS.reset()
    TRACES.reset()
    result = SimulationEngine(
        arm="spark", seed=seed, personas=personas, weeks=weeks
    ).run()
    totals = result.totals
    return {
        "offered": totals.encounters_offered,
        "accepted": totals.encounters_accepted,
        "connections": totals.mutual_connects,
        "lockins": totals.lockins_opened,
        "alive_at_week_4": totals.lockins_active_at_week_4,
        "quiet_user_days": totals.days_without_candidate,
        "gini": round(result.metrics["encounter_gini"], 3),
    }


def sweep_cooldown(values: list[int], weeks: int, personas: int, seed: int) -> list[dict]:
    """Open question 1: how much encounter supply does the cooldown cost?"""
    import src.config as config

    original = SETTINGS.rules
    rows = []
    for days in values:
        # Patch the live settings object the agents read. Restored below.
        config.SETTINGS = replace(
            SETTINGS, rules=replace(original, rematch_cooldown_days=days)
        )
        _repoint(config.SETTINGS)
        row = {"cooldown_days": days, **_run(weeks, personas, seed)}
        rows.append(row)
        print(
            f"  cooldown {days:>3}d: {row['offered']:>5} offered, "
            f"{row['connections']:>3} connections, "
            f"{row['quiet_user_days']:>5} quiet user-days, Gini {row['gini']}"
        )
    config.SETTINGS = replace(SETTINGS, rules=original)
    _repoint(config.SETTINGS)
    return rows


def sweep_lockins(values: list[int], weeks: int, personas: int, seed: int) -> list[dict]:
    """Open question 2: what does the lock-in ceiling actually change?"""
    import src.config as config

    original = SETTINGS.rules
    rows = []
    for ceiling in values:
        config.SETTINGS = replace(SETTINGS, rules=replace(original, max_lockins=ceiling))
        _repoint(config.SETTINGS)
        row = {"max_lockins": ceiling, **_run(weeks, personas, seed)}
        rows.append(row)
        print(
            f"  ceiling {ceiling:>2}: {row['lockins']:>3} lock-ins opened, "
            f"{row['alive_at_week_4']:>3} alive at week 4, Gini {row['gini']}"
        )
    config.SETTINGS = replace(SETTINGS, rules=original)
    _repoint(config.SETTINGS)
    return rows


def _repoint(settings) -> None:
    """Point the modules that imported SETTINGS by value at the new object.

    `from src.config import SETTINGS` binds the name at import time, so
    replacing `config.SETTINGS` alone would leave every agent reading the old
    rules. Only this sweep needs to do it; nothing else mutates settings at
    runtime, which is why `Settings` is otherwise frozen.
    """
    import src.agents.continuity
    import src.agents.delivery
    import src.mcp.services
    import src.safety.consent
    import src.safety.trust
    import src.sim.engine

    for module in (
        src.safety.consent, src.safety.trust, src.agents.delivery,
        src.agents.continuity, src.mcp.services, src.sim.engine,
    ):
        module.SETTINGS = settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweeps for the parameters we guessed.")
    parser.add_argument("--cooldown", type=int, nargs="*", default=None,
                        help="rematch cooldown values in days, e.g. --cooldown 0 7 14 30")
    parser.add_argument("--lockins", type=int, nargs="*", default=None,
                        help="lock-in ceilings, e.g. --lockins 3 5 8")
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--personas", type=int, default=120)
    parser.add_argument("--seed", type=int, default=SETTINGS.sim.seed)
    args = parser.parse_args(argv)
    use_utf8()

    if args.cooldown is None and args.lockins is None:
        args.cooldown = [0, 7, 14, 30]

    print(
        f"Sweeping with {args.personas} personas x {args.weeks} weeks, seed "
        f"{args.seed}. Every other parameter is held fixed."
    )
    payload: dict = {"weeks": args.weeks, "personas": args.personas, "seed": args.seed}

    if args.cooldown:
        print("\nOPEN QUESTION 1 — rematch cooldown (currently a guess at 30 days)")
        payload["cooldown"] = sweep_cooldown(
            args.cooldown, args.weeks, args.personas, args.seed
        )
        print(
            "\n  Read this as a cost, not a recommendation. Overlap is driven by\n"
            "  routine, so a person's pool is largely the same faces each day; a\n"
            "  long cooldown exhausts it. Whether the novelty is worth the supply\n"
            "  is a product judgement, and it needs the interviews CLAUDE.md is\n"
            "  still waiting on."
        )

    if args.lockins:
        print("\nOPEN QUESTION 2 — lock-in ceiling (chosen for attention scarcity)")
        rows = sweep_lockins(args.lockins, args.weeks, args.personas, args.seed)
        payload["lockins"] = rows
        if max((row["lockins"] for row in rows), default=0) < 10:
            # A table of zeros compared against a table of zeros is not a
            # finding. Say so rather than letting a reader draw one.
            print(
                "\n  TOO FEW LOCK-INS TO COMPARE. This run opened fewer than ten\n"
                "  lock-ins in total, so the ceiling was never the binding\n"
                "  constraint and the rows above differ only by noise. Re-run\n"
                "  larger, e.g. --personas 200 --weeks 6."
            )
        print(
            "\n  The ceiling is about attention, which this simulation does not\n"
            "  model: simulated people never get overwhelmed. Treat a higher\n"
            "  ceiling looking 'better' here as a limitation of the simulator."
        )

    out = RUNS_DIR / "sweeps.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
