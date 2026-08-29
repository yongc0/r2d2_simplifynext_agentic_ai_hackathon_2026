"""`mark_internal()` must not reach across execution contexts.

Spans created inside `mark_internal()` are tagged so `/api/events` can drop
them: the starter search is the demo choosing whose day to follow, not agent
work, and twenty rows of it made the Director panel's central claim — that every
row is an agent doing something — false.

It was implemented as a module-level integer. The API is a server, so while one
request sat inside the block for its starter search, spans created by *another*
request were tagged internal too and vanished from that viewer's panel. A flag
that silently hides someone else's agent work is worse than the noise it was
added to remove: the panel looks fine and is simply missing things.

`ContextVar` fixes it because each request, and each thread, gets its own value.
"""

from __future__ import annotations

import threading

from src.telemetry.trace import (
    INTERNAL_ATTRIBUTE,
    TRACES,
    is_internal,
    mark_internal,
    span,
)


def spans_named(name: str):
    return [s for s in TRACES.spans if s.name == name]


def only(name: str):
    matches = spans_named(name)
    assert len(matches) == 1, f"expected exactly one {name!r}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# The basics
# ---------------------------------------------------------------------------


def test_a_span_outside_the_block_is_not_internal() -> None:
    with span("ctx.plain"):
        pass
    assert not is_internal(only("ctx.plain"))


def test_a_span_inside_the_block_is_internal() -> None:
    with mark_internal():
        with span("ctx.inside"):
            pass
    assert is_internal(only("ctx.inside"))


def test_the_block_stops_applying_when_it_ends() -> None:
    with mark_internal():
        with span("ctx.during"):
            pass
    with span("ctx.after"):
        pass

    assert is_internal(only("ctx.during"))
    assert not is_internal(only("ctx.after"))


# ---------------------------------------------------------------------------
# Nesting and unwinding
# ---------------------------------------------------------------------------


def test_nested_blocks_stay_internal_until_the_outermost_exits() -> None:
    """The inner block ending must not un-mark the outer one.

    This is why the depth is a count rather than a boolean, and why it is
    restored by token rather than by decrementing.
    """
    with mark_internal():
        with mark_internal():
            with span("ctx.nested.inner"):
                pass
        # Still inside the OUTER block.
        with span("ctx.nested.middle"):
            pass
    with span("ctx.nested.outside"):
        pass

    assert is_internal(only("ctx.nested.inner"))
    assert is_internal(only("ctx.nested.middle"))
    assert not is_internal(only("ctx.nested.outside"))


def test_an_exception_still_restores_the_previous_value() -> None:
    """An early exit must not leave the flag stuck on.

    Stuck on, every later span in that context would be hidden from the panel —
    the failure mode is silence, which is exactly the one nobody notices.
    """

    class Boom(Exception):
        pass

    try:
        with mark_internal():
            raise Boom()
    except Boom:
        pass

    with span("ctx.after_exception"):
        pass
    assert not is_internal(only("ctx.after_exception"))


def test_an_exception_inside_a_nested_block_unwinds_one_level() -> None:
    class Boom(Exception):
        pass

    with mark_internal():
        try:
            with mark_internal():
                raise Boom()
        except Boom:
            pass
        # The outer block is still in force.
        with span("ctx.unwound.inner"):
            pass
    with span("ctx.unwound.outer"):
        pass

    assert is_internal(only("ctx.unwound.inner"))
    assert not is_internal(only("ctx.unwound.outer"))


# ---------------------------------------------------------------------------
# The bug this replaced
# ---------------------------------------------------------------------------


def test_another_thread_is_not_marked_internal() -> None:
    """The actual defect, as a test.

    One thread holds `mark_internal()` open — a request doing its starter
    search. Another creates an ordinary agent span at the same moment. With a
    module-level integer the second span was tagged internal and disappeared
    from that viewer's Director panel.
    """
    inside = threading.Event()
    other_done = threading.Event()

    def holder() -> None:
        with mark_internal():
            with span("ctx.thread.internal"):
                pass
            inside.set()
            # Hold the block open across the other thread's work.
            other_done.wait(timeout=5)

    def other() -> None:
        inside.wait(timeout=5)
        with span("ctx.thread.agent"):
            pass
        other_done.set()

    a = threading.Thread(target=holder)
    b = threading.Thread(target=other)
    a.start()
    b.start()
    a.join(timeout=10)
    b.join(timeout=10)

    assert is_internal(only("ctx.thread.internal"))
    assert not is_internal(only("ctx.thread.agent")), (
        "a span from another thread was marked internal — it would be silently "
        "missing from that viewer's Director panel"
    )


def test_the_attribute_name_is_the_one_the_feed_reads() -> None:
    """`is_internal` and the feed must agree about the attribute, or the
    suppression quietly does nothing."""
    with mark_internal():
        with span("ctx.attribute"):
            pass
    record = only("ctx.attribute")
    assert record.attributes.get(INTERNAL_ATTRIBUTE) == "true"
    assert is_internal(record)


def test_the_starter_search_is_still_suppressed() -> None:
    """The behaviour the flag exists for, unchanged by the contextvar move."""
    from fastapi.testclient import TestClient

    from src.api.app import create_app

    client = TestClient(create_app())
    client.post("/api/demo/reset")
    start = len(TRACES.spans)
    client.post("/api/encounters")

    produced = TRACES.spans[start:]
    assert any(is_internal(s) for s in produced), "the search was not suppressed"
