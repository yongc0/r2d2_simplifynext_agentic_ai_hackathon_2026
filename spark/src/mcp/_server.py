"""Turns a row of the tool catalogue into a real MCP server.

Each of the six server modules is four lines because of this file. That is
deliberate: the interesting part of an MCP server is *which capabilities it
exposes and what they refuse to return*, and that is visible in `services.py`
and in the catalogue in `registry.py`. Repeating protocol boilerplate six times
would hide it.

Run any of them:

    uv run -m src.mcp.overlap        # stdio, the transport an MCP client uses

The world these servers read is seeded on import (`--seed` controls it) so a
judge who connects an MCP client to `spark-overlap` gets real data back rather
than an empty store.
"""

from __future__ import annotations

import sys

from mcp.server import MCPServer

from src.mcp.registry import TOOLS

#: What each server is for, in one line, as an MCP client sees it.
_INSTRUCTIONS: dict[str, str] = {
    "spark-overlap": (
        "Whose path crossed whose, on days that have already happened. Returns "
        "opaque cell tokens and coarse time buckets. There is no live-proximity "
        "tool here and there will not be one: it is a de-anonymisation and "
        "stalking vector (docs/ARCHITECTURE.md §13.3)."
    ),
    "spark-profile": (
        "Matchable profiles and per-user continuity memory. Identity fields are "
        "never returned. Notes are scoped to their owner and expire."
    ),
    "spark-voice": (
        "The anonymous voice bridge. Both legs are anonymous, and every call "
        "stops at 180 seconds — the duration is not a parameter."
    ),
    "spark-calendar": "Coarse availability, for choosing when rather than where.",
    "spark-venue": (
        "Date options ranked on fit with a pair's shared interests. Commercial "
        "partners are labelled and cannot influence the ranking."
    ),
    "spark-sim": "The simulated world: personas, and the evaluation arms.",
    "spark-places": (
        "Real venues from OpenStreetMap, fetched once and committed — never a "
        "live call. Returns names, addresses and coordinates, and is the only "
        "server that does. It is never given a user id, a cell or an overlap "
        "history, so it cannot rank by proximity to anybody; venues reach a "
        "person only inside a post-reveal date plan (docs/ARCHITECTURE.md "
        "§13.6). Missing opening hours are reported UNKNOWN, never assumed open."
    ),
}


def build_server(server_name: str, seed_world: bool = True) -> MCPServer:
    """Build the MCP server that exposes `server_name`'s tools."""
    specs = TOOLS.get(server_name)
    if specs is None:
        raise SystemExit(
            f"{server_name!r} is not one of the Spark MCP servers. "
            f"Available: {', '.join(sorted(TOOLS))}."
        )
    if seed_world:
        # Imported here rather than at module scope: the simulator pulls in the
        # agents, and an MCP server should not need the agent layer to answer a
        # tool call.
        from src.sim.world import seed_world_if_empty

        seed_world_if_empty()

    server = MCPServer(
        name=server_name,
        version="0.1.0",
        instructions=_INSTRUCTIONS.get(server_name, ""),
    )
    for spec in specs:
        server.add_tool(spec.fn, name=spec.name, description=spec.description)
    return server


def run(server_name: str) -> None:
    """Serve over stdio. This is what `uv run -m src.mcp.<name>` does."""
    server = build_server(server_name)
    print(
        f"{server_name}: serving {len(TOOLS[server_name])} tools over stdio",
        file=sys.stderr,
    )
    server.run(transport="stdio")
