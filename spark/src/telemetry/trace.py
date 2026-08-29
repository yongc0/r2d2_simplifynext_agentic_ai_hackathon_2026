"""OpenTelemetry setup, and the only two tracing calls agent code may make.

Why this file exists rather than agents importing the OTEL SDK: an unspanned
call is invisible in the demo, and the demo *is* the trace. Funnelling every
span through `span()` and `@traced` means adding an agent cannot accidentally
skip instrumentation, and it gives one place to scrub attributes.

    from src.telemetry import span, traced

    with span("match.shortlist", pool_size=len(pool)) as s:
        ...
        s.set_attribute("selected", decision.candidate_id)

    @traced("continuity.brief")
    def build_brief(...): ...

Spans are collected in memory as well as exported, because the CLI prints a
tree of the encounter at the end of a run and the evaluation reads span
durations. `TRACES.tree()` is what `uv run -m src.cli.encounter` prints.
"""

from __future__ import annotations

import functools
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import ReadableSpan, Span, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from src.config import SETTINGS

#: Attribute names that must never reach a span. A key in a trace is a key in a
#: log file, and a log file outlives the run that wrote it.
_SECRET_HINTS = ("key", "secret", "token", "password", "credential", "authorization")

_MAX_ATTR_CHARS = 300


def _scrub(key: str, value: Any) -> Any:
    """Drop anything secret-shaped and bound anything long.

    Deliberately blunt: it is better to lose a debugging attribute than to
    write a credential into a trace that gets attached to a submission.
    """
    lowered = key.lower()
    if any(hint in lowered for hint in _SECRET_HINTS):
        return "[redacted]"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > _MAX_ATTR_CHARS:
        return text[: _MAX_ATTR_CHARS - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# In-memory collection — the CLI and the evaluation both read this
# ---------------------------------------------------------------------------


@dataclass
class SpanRecord:
    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start_ns: int
    end_ns: int
    attributes: dict[str, Any]
    status: str

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000


@dataclass
class TraceCollector:
    """Every span this process produced, in finish order."""

    spans: list[SpanRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, record: SpanRecord) -> None:
        with self._lock:
            self.spans.append(record)

    def reset(self) -> None:
        with self._lock:
            self.spans.clear()

    def for_trace(self, trace_id: str) -> list[SpanRecord]:
        return [s for s in self.spans if s.trace_id == trace_id]

    def tree(self, trace_id: str | None = None, show_attributes: bool = True) -> str:
        """Render one trace as an indented tree — this is the demo artefact.

        Spans finish inside-out, so the collection order is not the display
        order; children are looked up by parent id and printed under their
        parent in start order.
        """
        spans = self.for_trace(trace_id) if trace_id else list(self.spans)
        if not spans:
            return "(no spans recorded)"
        by_parent: dict[str | None, list[SpanRecord]] = {}
        known = {s.span_id for s in spans}
        for s in sorted(spans, key=lambda s: s.start_ns):
            # A parent outside this trace slice becomes a root, so nothing is
            # silently dropped from the picture.
            parent = s.parent_id if s.parent_id in known else None
            by_parent.setdefault(parent, []).append(s)

        lines: list[str] = []

        def walk(parent: str | None, depth: int) -> None:
            for s in by_parent.get(parent, []):
                # OTEL leaves a successful span UNSET; only ERROR is a problem,
                # and it is the one thing the tree must make impossible to miss.
                mark = " !" if s.status == "ERROR" else "  "
                indent = "  " * depth
                lines.append(f"{indent}{mark}{s.name}  ({s.duration_ms:.1f} ms)")
                if show_attributes:
                    for k, v in sorted(s.attributes.items()):
                        if k.startswith("internal."):
                            continue
                        lines.append(f"{indent}      {k} = {v}")
                walk(s.span_id, depth + 1)

        walk(None, 0)
        return "\n".join(lines)


#: The process-wide collector. Tests reset it; the CLI prints it.
TRACES = TraceCollector()


class _CollectingExporter(SpanExporter):
    """Feeds `TRACES`, and optionally a JSONL file for the recording."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._handle = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = path.open("a", encoding="utf-8")

    def export(self, spans: tuple[ReadableSpan, ...]) -> SpanExportResult:  # type: ignore[override]
        for s in spans:
            ctx = s.get_span_context()
            record = SpanRecord(
                name=s.name,
                trace_id=format(ctx.trace_id, "032x"),
                span_id=format(ctx.span_id, "016x"),
                parent_id=format(s.parent.span_id, "016x") if s.parent else None,
                start_ns=s.start_time or 0,
                end_ns=s.end_time or 0,
                attributes=dict(s.attributes or {}),
                status=s.status.status_code.name if s.status else "UNSET",
            )
            TRACES.add(record)
            if self._handle is not None:
                self._handle.write(json.dumps(record.__dict__, default=str) + "\n")
        if self._handle is not None:
            self._handle.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


_provider: TracerProvider | None = None
_tracer: otel_trace.Tracer | None = None
_setup_lock = threading.Lock()


def setup_tracing(to_file: bool = False) -> otel_trace.Tracer:
    """Install the tracer provider once per process and return the tracer.

    Idempotent: calling it from the CLI, a test and an agent all reach the same
    provider. OTEL itself warns and ignores a second `set_tracer_provider`, so
    the guard is ours rather than theirs.
    """
    global _provider, _tracer
    with _setup_lock:
        if _tracer is not None:
            return _tracer
        _provider = TracerProvider()
        _provider.add_span_processor(
            SimpleSpanProcessor(
                _CollectingExporter(SETTINGS.trace_file if to_file else None)
            )
        )
        otel_trace.set_tracer_provider(_provider)
        _tracer = _provider.get_tracer("spark")
        return _tracer


def _tracer_or_setup() -> otel_trace.Tracer:
    return _tracer if _tracer is not None else setup_tracing()


#: Set while THIS execution context is doing housekeeping rather than agent work.
#:
#: Spans created inside `mark_internal()` are tagged, and `/api/events` drops
#: them. They stay in the trace file — this hides them from the Director PANEL,
#: it does not hide them from anyone debugging. The distinction matters: the
#: panel's claim is that every row is an agent doing something, and twenty rows
#: of the demo deciding whose day to follow makes that claim false.
#:
#: A `ContextVar`, NOT a module-level integer. It was a plain global, and the
#: API is a server: while one request sat inside `mark_internal()` for its
#: starter search, every span another request created was tagged internal too
#: and vanished from that viewer's panel. A flag that silently hides another
#: request's agent work is worse than the noise it was added to remove.
#:
#: `ContextVar` gives each request — and each thread, since a new thread starts
#: from a fresh context — its own depth, with no locking and no bookkeeping.
_INTERNAL_DEPTH: ContextVar[int] = ContextVar("spark_internal_depth", default=0)

#: Attribute name carried by such spans.
INTERNAL_ATTRIBUTE = "spark.internal"


@contextmanager
def mark_internal() -> Iterator[None]:
    """Tag every span created in this block, in THIS context, as machinery.

    Nests, and unwinds correctly on an exception: `set()` returns a token and
    `reset(token)` restores the exact previous value rather than decrementing a
    counter that an early exit might have skipped.
    """
    token = _INTERNAL_DEPTH.set(_INTERNAL_DEPTH.get() + 1)
    try:
        yield
    finally:
        _INTERNAL_DEPTH.reset(token)


def is_internal(record) -> bool:
    """Whether a collected span was machinery. Used by the events feed."""
    return str(record.attributes.get(INTERNAL_ATTRIBUTE, "")).lower() == "true"


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """Open a span. The one call agent code makes.

    Exceptions are recorded on the span and re-raised — a failed agent call
    stays visible in the trace instead of vanishing.
    """
    tracer = _tracer_or_setup()
    with tracer.start_as_current_span(name) as current:
        if _INTERNAL_DEPTH.get() > 0:
            current.set_attribute(INTERNAL_ATTRIBUTE, "true")
        for key, value in attributes.items():
            current.set_attribute(key, _scrub(key, value))
        started = time.perf_counter()
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(exc)))
            raise
        finally:
            current.set_attribute("duration_ms", round((time.perf_counter() - started) * 1000, 2))


def traced(name: str, **static_attributes: Any):
    """Decorator form, for a function that is a whole step on its own."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with span(name, **static_attributes):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def current_trace_id() -> str:
    """The active trace id as hex, or "" outside a span.

    `Encounter.trace_id` is set from this, which is what lets an operator go
    from a six-week-old encounter row to the trace that produced it.
    """
    ctx = otel_trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return ""
    return format(ctx.trace_id, "032x")


def set_attribute(key: str, value: Any) -> None:
    """Add an attribute to whatever span is currently open, if any."""
    current = otel_trace.get_current_span()
    if current.get_span_context().is_valid:
        current.set_attribute(key, _scrub(key, value))
