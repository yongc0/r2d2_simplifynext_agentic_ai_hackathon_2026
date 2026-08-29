"""What every agent shares: the loop cap, and the shape of an agent.

CLAUDE.md: *every reasoning loop has a hard cap. Default 5 iterations, from
config, never a magic number in the loop. Log when the cap is hit.* Loop
discipline is one of the six graded metrics, so the cap is a helper rather than
a convention — an agent cannot forget to apply it if applying it is how the
loop is written.

    for attempt in bounded_loop("match"):
        candidate = propose(attempt)
        if acceptable(candidate):
            break

`bounded_loop` yields 1..cap, records the iteration count when the loop leaves,
and logs a cap hit as an actionable failure rather than a silent one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from src.config import SETTINGS
from src.telemetry.metrics import METRICS
from src.telemetry.trace import set_attribute


@dataclass
class LoopReport:
    """Filled in as the loop runs, so a caller can see what happened."""

    agent: str
    iterations: int = 0
    hit_cap: bool = False


@contextmanager
def loop_report(agent: str, cap: int | None = None) -> Iterator[LoopReport]:
    """Record loop discipline for a block that iterates in its own way.

    For agents whose reasoning is not a `for` loop — a shortlist narrowed in
    passes, say. The counting is manual; the recording is not.
    """
    cap = SETTINGS.loop.max_iterations if cap is None else cap
    report = LoopReport(agent=agent)
    try:
        yield report
    finally:
        report.hit_cap = report.iterations >= cap
        METRICS.record_loop(agent, report.iterations, cap)
        set_attribute("loop.iterations", report.iterations)
        set_attribute("loop.cap", cap)
        set_attribute("loop.hit_cap", report.hit_cap)


def bounded_loop(agent: str, cap: int | None = None) -> Iterator[int]:
    """Iterate at most `cap` times, and record how many times it actually did.

    Yields 1-based attempt numbers so a prompt can honestly say "attempt 2 of
    5". Breaking out early is the normal case and is what a healthy cap-hit
    rate looks like: §17 targets under 2% of runs reaching the cap.
    """
    # `cap is None`, not `cap or ...`: an explicit cap of 0 is a misconfiguration
    # to reject, and `0 or 5` would silently turn it into five iterations.
    cap = SETTINGS.loop.max_iterations if cap is None else cap
    if cap < 1:
        raise ValueError(
            f"loop cap for {agent} is {cap}; it must be at least 1. "
            "Set SPARK_MAX_LOOP_ITERATIONS to a positive integer."
        )
    completed = 0
    try:
        for attempt in range(1, cap + 1):
            completed = attempt
            yield attempt
    finally:
        METRICS.record_loop(agent, completed, cap)
        set_attribute("loop.iterations", completed)
        set_attribute("loop.cap", cap)


#: The organisers' eight agent classes (§4). Every agent module names its own
#: in its docstring and in `AGENT_CLASS`, so the claim on the architecture
#: slide — seven of eight — is checkable in code rather than asserted on a
#: slide. `tests/test_schemas.py` reads these.
AGENT_CLASSES = (
    "Information",
    "Extraction",
    "Transaction",
    "Decision-Support",
    "Creative/Generative",
    "Orchestration",
    "Personalized",
    "Embedded",
)
