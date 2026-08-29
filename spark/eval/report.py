"""The metric tables for the slides.

    uv run -m eval.report
    uv run -m eval.report --json          # machine-readable, for the deck build

Prints four things:

  1. The six metrics the organisers named (§17), with their targets.
  2. The four metrics specific to this product (§18).
  3. The three-arm comparison (§19), with a significance test and a plain
     statement of the pre-registered result.
  4. What the run could not do, and what fell back — never omitted.

On the significance test. Two-proportion z-test, written out rather than
imported, because adding scipy to run one formula is not a dependency anyone
should have to install to check our arithmetic. It is a normal approximation,
which needs roughly ten successes and ten failures per arm to be trustworthy;
when a run has fewer, the report says so instead of quoting a p-value it cannot
support.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from src.cli._console import use_utf8
from src.config import RUNS_DIR, SETTINGS

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def two_proportion_test(
    hits_a: int, total_a: int, hits_b: int, total_b: int
) -> dict[str, float | str | None]:
    """Is arm A's rate distinguishable from arm B's?

    Returns the two rates, the difference, a z statistic and a two-sided p, or
    an explanation of why the test does not apply. A p-value from four
    successes is decoration, and this reports that rather than printing one.
    """
    if total_a == 0 or total_b == 0:
        return {"applicable": False, "reason": "one arm produced no trials"}
    rate_a, rate_b = hits_a / total_a, hits_b / total_b
    expected = [
        hits_a, total_a - hits_a, hits_b, total_b - hits_b,
    ]
    if min(expected) < 10:
        return {
            "applicable": False,
            "rate_a": rate_a,
            "rate_b": rate_b,
            "difference": rate_a - rate_b,
            "reason": (
                f"the normal approximation needs at least 10 successes and 10 "
                f"failures per arm; the smallest cell here is {min(expected)}. "
                "Run more seeds (--seeds) before reading anything into this."
            ),
        }
    pooled = (hits_a + hits_b) / (total_a + total_b)
    standard_error = math.sqrt(pooled * (1 - pooled) * (1 / total_a + 1 / total_b))
    if standard_error == 0:
        return {"applicable": False, "reason": "zero variance"}
    z = (rate_a - rate_b) / standard_error
    p = 2 * (1 - _normal_cdf(abs(z)))
    return {
        "applicable": True,
        "rate_a": rate_a,
        "rate_b": rate_b,
        "difference": rate_a - rate_b,
        "z": z,
        "p": p,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def pool_by_arm(runs: list[dict]) -> dict[str, dict]:
    """Sum the counters across seeds.

    Counters are pooled, not averaged: an average of three rates weights a
    quiet world the same as a busy one, and the pooled rate is the one that
    answers "what happened across everything we ran".
    """
    pooled: dict[str, dict] = defaultdict(
        lambda: {"totals": defaultdict(int), "metrics": [], "seeds": [], "notes": [],
                 "continuity_examples": [], "lockin_detail": defaultdict(int)}
    )
    for run in runs:
        arm = pooled[run["arm"]]
        for key, value in run["totals"].items():
            arm["totals"][key] += value
        for key, value in run["lockin_detail"].items():
            if isinstance(value, (int, float)) and value is not None:
                arm["lockin_detail"][key] += value
        arm["metrics"].append(run["metrics"])
        arm["seeds"].append(run["seed"])
        arm["notes"].extend(run["notes"])
        if run["continuity_examples"] and not arm["continuity_examples"]:
            arm["continuity_examples"] = run["continuity_examples"]
    return {k: dict(v, totals=dict(v["totals"])) for k, v in pooled.items()}


def _sum_metric(metrics: list[dict], path: tuple[str, ...], key: str) -> int:
    total = 0
    for snapshot in metrics:
        node = snapshot
        for part in path:
            node = node.get(part, {})
        total += node.get(key, 0) or 0
    return total


def _rate(hits: int, total: int) -> str:
    return "n/a (n=0)" if total == 0 else f"{hits / total:.2%} (n={total})"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _line(char: str = "-", width: int = 78) -> str:
    return char * width


def render(payload: dict) -> str:
    runs = payload["runs"]
    pooled = pool_by_arm(runs)
    provider = payload["provider"]
    out: list[str] = []

    out.append(_line("="))
    out.append("SPARK — EVALUATION REPORT")
    out.append(_line("="))
    out.append(
        f"{payload['personas']} personas · {payload['weeks']} weeks · "
        f"{payload['seeds']} seed(s) from {payload['base_seed']} · "
        f"provider: {provider}"
    )
    if provider == "deterministic":
        out.append(
            "NOTE: no model provider was configured for this run. Every judgement\n"
            "      call used the deterministic policy. Metrics 1 (schema validation)\n"
            "      and 4 (token cost) measure model outputs and are therefore n/a;\n"
            "      they are not zero, and are not reported as zero."
        )
    else:
        out.append(
            f"      reasoning tier: {payload['model_reasoning']}\n"
            f"      fast tier:      {payload['model_fast']}"
        )
    out.append("")

    spark = pooled.get("spark")
    if spark is None:
        out.append("The spark arm was not run, so the required metrics cannot be reported.")
        return "\n".join(out)

    # -- 1. the organisers' six --------------------------------------
    metrics = spark["metrics"]
    out.append(_line())
    out.append("1. THE SIX REQUIRED METRICS  (docs/ARCHITECTURE.md §17) — Spark arm")
    out.append(_line())
    out.append(f"{'metric':<34}{'result':<26}{'target':<18}")

    schema_hits = _sum_metric(metrics, ("schema_validation",), "hits")
    schema_total = _sum_metric(metrics, ("schema_validation",), "total")
    out.append(
        f"{'1 schema validation pass rate':<34}"
        f"{_rate(schema_hits, schema_total):<26}{'>= 98%':<18}"
    )

    tool_hits = _sum_metric(metrics, ("tool_calls",), "hits")
    tool_total = _sum_metric(metrics, ("tool_calls",), "total")
    out.append(
        f"{'2 tool-call success rate':<34}"
        f"{_rate(tool_hits, tool_total):<26}{'>= 95%':<18}"
    )

    cap_runs = sum(m["loop"]["runs"] for m in metrics)
    cap_rate = sum(
        (m["loop"]["cap_hit_rate"] or 0) * m["loop"]["runs"] for m in metrics
    ) / max(1, cap_runs)
    mean_iterations = sum(
        (m["loop"]["mean_iterations"] or 0) * m["loop"]["runs"] for m in metrics
    ) / max(1, cap_runs)
    out.append(
        f"{'3 loop discipline (at cap)':<34}"
        f"{f'{cap_rate:.2%} (n={cap_runs})':<26}{'< 2% at cap':<18}"
    )
    out.append(
        f"{'  mean iterations / cap':<34}"
        f"{f'{mean_iterations:.2f} / {SETTINGS.loop.max_iterations}':<26}"
    )

    total_cost = sum(m["total_cost_usd"] for m in metrics)
    llm_calls = sum(m["llm_calls"]["attempted"] for m in metrics)
    if llm_calls == 0:
        cost_cell = "n/a (no model calls)"
    elif total_cost == 0:
        cost_cell = f"{llm_calls} calls, unpriced"
    else:
        cost_cell = f"${total_cost:.4f} over {llm_calls} calls"
    out.append(f"{'4 token cost per run':<34}{cost_cell:<26}{'reported':<18}")

    completion_hits = _sum_metric(metrics, ("task_completion",), "hits")
    completion_total = _sum_metric(metrics, ("task_completion",), "total")
    out.append(
        f"{'5 task completion rate':<34}"
        f"{_rate(completion_hits, completion_total):<26}{'>= 90%':<18}"
    )
    out.append(
        "  (completion = reaching the human consent gate with no manual\n"
        "   intervention. Whether the humans said yes is not the system's score.)"
    )

    fidelity_hits = _sum_metric(metrics, ("answer_fidelity",), "hits")
    fidelity_total = _sum_metric(metrics, ("answer_fidelity",), "total")
    out.append(
        f"{'6 answer fidelity (grounded)':<34}"
        f"{_rate(fidelity_hits, fidelity_total):<26}{'>= 95%':<18}"
    )
    out.append("")

    # -- 2. our four ---------------------------------------------------
    out.append(_line())
    out.append("2. THE FOUR PRODUCT METRICS  (§18) — Spark arm")
    out.append(_line())
    leak_hits = _sum_metric(metrics, ("anonymity_leakage",), "hits")
    leak_total = _sum_metric(metrics, ("anonymity_leakage",), "total")
    out.append(
        f"{'anonymity leakage rate':<34}"
        f"{_rate(leak_hits, leak_total):<26}{'zero — non-negotiable':<18}"
    )
    out.append(
        f"  {leak_total} user-facing strings were screened before rendering; "
        f"{leak_hits} were refused."
    )

    ginis = [m["encounter_gini"] for m in metrics]
    out.append(
        f"{'encounter distribution (Gini)':<34}"
        f"{f'{sum(ginis) / len(ginis):.3f}':<26}{'lower is fairer':<18}"
    )

    fn_hits = _sum_metric(metrics, ("guardrail_false_negative",), "hits")
    fn_total = _sum_metric(metrics, ("guardrail_false_negative",), "total")
    if fn_total == 0:
        out.append(
            f"{'guardrail false-negative rate':<34}"
            f"{'see tests/test_mcp.py':<26}{'zero':<18}"
        )
        out.append(
            "  The adversarial set runs in the test suite rather than the "
            "simulation:\n  uv run pytest tests/test_mcp.py -k adversarial"
        )
    else:
        out.append(
            f"{'guardrail false-negative rate':<34}{_rate(fn_hits, fn_total):<26}{'zero':<18}"
        )

    connections = sum(m["mutual_connections"] for m in metrics)
    if connections and total_cost:
        out.append(
            f"{'cost per successful connection':<34}"
            f"{f'${total_cost / connections:.4f}':<26}"
        )
    else:
        out.append(
            f"{'cost per successful connection':<34}"
            f"{f'n/a ({connections} connections, unpriced)':<26}"
        )
        out.append(
            "  Set SPARK_PRICE_REASONING_IN / _OUT in .env from the provider's\n"
            "  current published rates. We do not hardcode a price that goes stale."
        )
    out.append("")

    # -- 3. the three arms --------------------------------------------
    out.append(_line())
    out.append("3. DOES THE MATCHING ADD ANYTHING?  (§19)")
    out.append(_line())
    out.append(
        f"{'arm':<13}{'offered':>9}{'accepted':>10}{'connects':>10}"
        f"{'accept%':>9}{'connect%':>10}{'met/14d':>9}{'alive@4w':>10}"
    )
    for arm in ("spark", "random", "similarity"):
        data = pooled.get(arm)
        if data is None:
            continue
        t = data["totals"]
        accept_rate = t["encounters_accepted"] / t["encounters_offered"] if t["encounters_offered"] else 0
        connect_rate = t["mutual_connects"] / t["calls_completed"] if t["calls_completed"] else 0
        out.append(
            f"{arm:<13}{t['encounters_offered']:>9}{t['encounters_accepted']:>10}"
            f"{t['mutual_connects']:>10}{accept_rate:>8.1%}{connect_rate:>10.1%}"
            f"{t['met_in_person_by_day_14']:>9}{t['lockins_active_at_week_4']:>10}"
        )
    out.append("")
    out.append(
        "  accept%   notifications accepted by BOTH parties\n"
        "  connect%  calls ending in yes from both sides — the pre-registered metric\n"
        "  alive@4w  lock-ins still active after four weeks — the north star"
    )
    out.append("")

    # -- the pre-registered result ------------------------------------
    out.append(_line())
    out.append("PRE-REGISTERED RESULT")
    out.append(_line())
    out.append(
        "CLAUDE.md, before any of this was run: *if the Match Agent does not beat\n"
        "random assignment on mutual connect rate, we report it.*\n"
    )
    for baseline in ("random", "similarity"):
        data = pooled.get(baseline)
        if data is None:
            continue
        test = two_proportion_test(
            spark["totals"]["mutual_connects"], spark["totals"]["calls_completed"],
            data["totals"]["mutual_connects"], data["totals"]["calls_completed"],
        )
        out.append(f"Spark vs {baseline}:")
        if not test.get("applicable"):
            if "rate_a" in test:
                out.append(
                    f"  Spark {test['rate_a']:.1%} vs {baseline} {test['rate_b']:.1%} "
                    f"(difference {test['difference']:+.1%})"
                )
            out.append(f"  NOT TESTABLE: {test['reason']}")
        else:
            verdict = (
                "distinguishable from noise"
                if test["p"] < 0.05
                else "NOT distinguishable from noise"
            )
            direction = "higher" if test["difference"] > 0 else "lower"
            out.append(
                f"  Spark {test['rate_a']:.1%} vs {baseline} {test['rate_b']:.1%} "
                f"— {abs(test['difference']):.1%} {direction}"
            )
            out.append(f"  z = {test['z']:.2f}, p = {test['p']:.3f} — {verdict}")
            if test["p"] >= 0.05:
                out.append(
                    "  We report this as it stands. The encounter format is the\n"
                    "  product; the matcher is an optimisation on top of it, and on\n"
                    "  this evidence we cannot claim it beats chance."
                )
        out.append("")

    # -- 4. what the run could not do ---------------------------------
    out.append(_line())
    out.append("4. WHAT THIS RUN COULD NOT DO")
    out.append(_line())
    # Aggregated across seeds. Three near-identical sentences differing only in
    # a count is noise; the count summed across the whole run is the fact.
    quiet = sum(run["totals"]["days_without_candidate"] for run in runs if run["arm"] == "spark")
    bridge = sum(run["totals"]["bridge_failures"] for run in runs if run["arm"] == "spark")
    seen = False
    if quiet:
        seen = True
        offered = spark["totals"]["encounters_offered"]
        out.append(
            f"  · {quiet} user-days ended with no eligible candidate in the "
            f"overlap pool,\n    against {offered} encounters offered. Those are "
            "quiet days, not failures —\n    nobody eligible crossed that "
            "person's path. The rematch cooldown is the\n    largest single "
            "cause; `uv run -m eval.sweeps` measures what it costs."
        )
    if bridge:
        seen = True
        out.append(
            f"  · {bridge} encounters were abandoned because the voice bridge "
            "failed.\n    Neither party was told the failure was ours, and the "
            "encounter is\n    re-offered the next day."
        )
    fallbacks = sum(m["llm_calls"]["fallbacks"] for m in metrics)
    if fallbacks:
        out.append(
            f"  · {fallbacks} decisions fell back to the deterministic policy. "
            "Nothing was dropped."
        )
    failures = sum(m["failures_total"] for m in metrics)
    if failures:
        out.append(f"  · {failures} logged failures across the run. Examples:")
        for snapshot in metrics[:1]:
            for failure in snapshot["failures"][:3]:
                out.append(f"      {failure['where']}: {failure['detail'][:100]}")
    if not seen and not fallbacks and not failures:
        out.append("  · Nothing was skipped, capped or dropped.")
    out.append("")

    # -- adaptation over time -----------------------------------------
    if spark["continuity_examples"]:
        out.append(_line())
        out.append("5. DOES IT ADAPT OVER TIME?")
        out.append(_line())
        out.append("  The same lock-in, weeks apart, from the run above:")
        for example in spark["continuity_examples"]:
            out.append(f"    {example}")
        out.append("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metric tables for the slides.")
    parser.add_argument("--input", default=str(RUNS_DIR / "arms.json"))
    parser.add_argument("--json", action="store_true", help="emit JSON instead of tables")
    args = parser.parse_args(argv)
    use_utf8()

    path = Path(args.input)
    if not path.exists():
        print(
            f"{path} does not exist. Produce it first with:\n"
            "    uv run -m eval.run_arms",
            file=sys.stderr,
        )
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))

    if args.json:
        pooled = pool_by_arm(payload["runs"])
        spark = pooled.get("spark", {"totals": {}})
        summary = {
            "provider": payload["provider"],
            "arms": {arm: data["totals"] for arm, data in pooled.items()},
            "pre_registered": {
                baseline: two_proportion_test(
                    spark["totals"].get("mutual_connects", 0),
                    spark["totals"].get("calls_completed", 0),
                    pooled[baseline]["totals"]["mutual_connects"],
                    pooled[baseline]["totals"]["calls_completed"],
                )
                for baseline in ("random", "similarity")
                if baseline in pooled
            },
        }
        print(json.dumps(summary, indent=2))
        return 0

    report = render(payload)
    print(report)
    destination = RUNS_DIR / "report.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report, encoding="utf-8")
    print(f"(also written to {destination})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
