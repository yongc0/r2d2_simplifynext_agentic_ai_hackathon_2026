"""Observability. One trace per encounter and per continuity action (§11.6).

`trace.py`    OTEL setup and the two helpers agent code is allowed to use.
`metrics.py`  the six metrics the organisers named, plus the four that would
              actually sink this product if they went wrong.

CLAUDE.md: agent code never touches the OTEL SDK directly. It calls `span()`
or `@traced`, and it never constructs a metric record by hand — it calls a
`METRICS.record_*` method. Both rules exist so that adding an agent cannot
accidentally make it invisible.
"""

from src.telemetry.metrics import METRICS, MetricsRegistry
from src.telemetry.trace import (
    TRACES,
    current_trace_id,
    setup_tracing,
    span,
    traced,
)

__all__ = [
    "METRICS",
    "MetricsRegistry",
    "TRACES",
    "current_trace_id",
    "setup_tracing",
    "span",
    "traced",
]
