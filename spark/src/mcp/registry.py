"""The tool catalogue, and the one client every agent calls.

Agent code never imports `services.py` directly. It calls:

    client.call("spark-overlap", "overlap_pool", user_id=..., day=...)

which is where three things happen that must happen on *every* tool call:

  the call is wrapped in a span, so it appears in the trace;
  the outcome is recorded, which is the tool-call success rate (metric 2);
  a failure is re-raised with a message an operator can act on.

`TOOLS` is also what the seven server modules publish over MCP, so the
catalogue a judge sees over stdio and the catalogue the simulation uses are one
list.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.mcp import places, services
from src.mcp.services import ToolFailure
from src.telemetry.metrics import METRICS
from src.telemetry.trace import span


class ToolError(RuntimeError):
    """A tool call that did not produce a usable result.

    Carries the server and tool name so the message is self-locating: an agent
    catching this can say what it is falling back from.
    """

    def __init__(self, server: str, tool: str, detail: str) -> None:
        super().__init__(f"{server}.{tool}: {detail}")
        self.server = server
        self.tool = tool
        self.detail = detail


@dataclass(frozen=True)
class ToolSpec:
    server: str
    name: str
    fn: Callable[..., dict[str, Any]]
    description: str


def _spec(server: str, fn: Callable[..., dict[str, Any]], description: str) -> ToolSpec:
    return ToolSpec(server=server, name=fn.__name__, fn=fn, description=description)


#: The seven servers and everything they expose. This is the architecture
#: slide's bottom row, as data.
TOOLS: dict[str, list[ToolSpec]] = {
    "spark-overlap": [
        _spec(
            "spark-overlap",
            services.overlap_pool,
            "Everyone whose path crossed a user on a given past day. Coarse cell "
            "token and time bucket only — never a coordinate, a place or a distance.",
        ),
        _spec(
            "spark-overlap",
            services.overlap_strength,
            "How many times two paths crossed in a recent window. A shared routine "
            "is a better reason for three minutes than a single coincidence.",
        ),
    ],
    "spark-profile": [
        _spec(
            "spark-profile",
            services.get_profile,
            "The matchable profile for a user. Never returns identity fields.",
        ),
        _spec(
            "spark-profile",
            services.write_note,
            "Store a continuity note in one user's own memory (AgentCore Memory).",
        ),
        _spec(
            "spark-profile",
            services.read_notes,
            "Read one user's own continuity notes. Expired notes are excluded.",
        ),
        _spec(
            "spark-profile",
            services.forget_notes,
            "Delete a user's continuity notes on request, and say how many went.",
        ),
    ],
    "spark-voice": [
        _spec(
            "spark-voice",
            services.connect_call,
            "Bridge two anonymous legs and stop at 180 seconds. Duration is not a "
            "parameter; there is no way to ask for a longer call.",
        ),
        _spec(
            "spark-voice",
            services.call_record,
            "What happened on a bridged call: when it started, how long, why it ended.",
        ),
    ],
    "spark-calendar": [
        _spec("spark-calendar", services.availability, "A user's typical free buckets."),
        _spec(
            "spark-calendar",
            services.shared_availability,
            "Time buckets two users are both typically free in.",
        ),
    ],
    "spark-venue": [
        _spec(
            "spark-venue",
            services.suggest_venues,
            "Date options ranked on fit with shared interests. Commercial partners "
            "are labelled and cannot influence the ranking.",
        ),
    ],
    "spark-sim": [
        _spec("spark-sim", services.sim_users, "Every user id in the simulated world."),
        _spec("spark-sim", services.sim_stats, "Size of the simulated world."),
    ],
    # Real venues, from OpenStreetMap, fetched once and committed. The only
    # server that returns a coordinate — and the only one that is never told
    # where a user is, which is what keeps it on the right side of invariant 3.
    "spark-places": [
        _spec(
            "spark-places",
            places.places_available,
            "Whether real venue data is loaded, and how much of it has opening "
            "hours. False means the planner shows an unavailable state; it "
            "never invents a venue.",
        ),
        _spec(
            "spark-places",
            places.search_places,
            "Venues matching shared interests, a budget and an energy level. "
            "Takes no location and no user id, so it cannot rank by proximity "
            "to anybody.",
        ),
        _spec(
            "spark-places",
            places.travel_between,
            "A walking-time estimate between two coordinates. Labelled an "
            "estimate everywhere it is shown; not a routed journey.",
        ),
        _spec(
            "spark-places",
            places.is_open_at,
            "open / closed / unknown for a venue at an hour. Missing hours are "
            "UNKNOWN, never assumed open — that is how a plan sends somebody "
            "to a locked door.",
        ),
    ],
}


def find(server: str, tool: str) -> ToolSpec:
    specs = TOOLS.get(server)
    if specs is None:
        raise ToolError(
            server,
            tool,
            f"no such MCP server. Available: {', '.join(sorted(TOOLS))}.",
        )
    for spec in specs:
        if spec.name == tool:
            return spec
    raise ToolError(
        server,
        tool,
        f"no such tool on {server}. Available: "
        f"{', '.join(s.name for s in specs)}.",
    )


@dataclass
class MCPClient:
    """The in-process transport.

    Same function bodies as the stdio servers, no subprocess. A six-week run
    over 200 personas makes far too many tool calls for six spawned processes
    per call to be viable, and the point of the MCP boundary is the *interface*
    — swapping this for a stdio or Gateway client is a transport change, which
    is precisely what §16 claims and what `src/mcp/overlap.py` demonstrates.
    """

    #: Set false in tests that want to assert on raw exceptions.
    record_metrics: bool = True

    def call(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        spec = find(server, tool)
        # `None` is not a valid OTEL attribute value, and an optional argument
        # left unset is the normal case rather than an error — dropping it keeps
        # the trace readable instead of emitting a warning per call.
        attributes = {
            f"arg.{k}": v for k, v in arguments.items() if v is not None
        }
        with span(f"mcp.{server}.{tool}", **attributes) as s:
            try:
                result = spec.fn(**arguments)
            except ToolFailure as exc:
                # A tool that failed for a reason it can explain. The message
                # is already actionable — pass it through rather than wrapping
                # it in something vaguer.
                if self.record_metrics:
                    METRICS.record_tool_call(server, tool, ok=False, detail=str(exc))
                s.set_attribute("ok", False)
                raise ToolError(server, tool, str(exc)) from exc
            except TypeError as exc:
                # Wrong arguments — a programming error, not a service outage.
                # Named as such so nobody spends an afternoon on the network.
                detail = (
                    f"called with {sorted(arguments)} but the tool signature "
                    f"rejected it ({exc}). This is a caller bug, not an outage."
                )
                if self.record_metrics:
                    METRICS.record_tool_call(server, tool, ok=False, detail=detail)
                s.set_attribute("ok", False)
                raise ToolError(server, tool, detail) from exc
            if self.record_metrics:
                METRICS.record_tool_call(server, tool, ok=True)
            s.set_attribute("ok", True)
            return result

    def try_call(
        self, server: str, tool: str, *, default: dict[str, Any] | None = None, **arguments: Any
    ) -> dict[str, Any] | None:
        """Call, and return `default` instead of raising.

        For the calls where a missing answer is survivable — a venue list, an
        availability lookup — so that one flaky tool does not abandon an
        encounter. The failure is still recorded; nothing is swallowed.
        """
        try:
            return self.call(server, tool, **arguments)
        except ToolError:
            return default


def catalogue() -> list[dict[str, str]]:
    """Every tool, flat. Printed by the CLI so the tool surface is visible
    without reading the code."""
    return [
        {"server": spec.server, "tool": spec.name, "description": spec.description}
        for specs in TOOLS.values()
        for spec in specs
    ]
