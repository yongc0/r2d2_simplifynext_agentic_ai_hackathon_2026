"""`spark-places` — real venues, with coordinates, hours and travel times.

The seventh MCP server, and it exists for the same reason as the other six:
every external capability is a tool, so the simulation and the demo call the
same interface and a judge can see where the outside world enters.

WHERE THE DATA COMES FROM

`data/venues_osm.json`, fetched once from OpenStreetMap by
`scripts/fetch_venues.py` and committed. Never a live call: a demo that queries
a public API on stage fails when the wifi does, and a plan that changes between
takes cannot be filmed twice.

WHAT IT REFUSES TO DO

If the file is absent this returns `available: False` and an empty list. It does
NOT fall back to inventing venues. A fabricated address is worse than no
suggestion — it is a real person standing outside a building that was never
there — and the requirement is explicit that an unavailable state is handled
rather than filled in.

Opening hours are the same rule. OpenStreetMap's coverage is patchy, so a venue
with no `opening_hours` tag is reported as UNKNOWN and rendered as unknown. It
is never assumed open.

HOW THIS COEXISTS WITH INVARIANT 3

Invariant 3 forbids rendering a place, and this server returns names, addresses
and coordinates. The reconciliation is the one already written into
ARCHITECTURE §13.6 for date planning, extended:

  WHEN — venues reach a user only through an itinerary, and itineraries are
  post-reveal only. Two people who have exchanged names and are choosing where
  to meet are picking a destination together.

  WHAT — this server is never given a user id, a cell, or anyone's overlap
  history. It cannot rank by proximity to a person because it is not told
  where any person is. `search()` takes interests and a budget; `travel()`
  takes two venues. Neither can express "near where you both were".
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.mcp.venue_rules import clean_venue

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "venues_osm.json"

#: Walking metres per minute. A deliberately plain estimate rather than a
#: routing call: OSRM is another live dependency, and "12 minutes" from a real
#: router is no more useful to a date plan than "about 12 minutes" from
#: arithmetic. Stated so nobody mistakes it for measured.
WALK_METRES_PER_MINUTE = 78.0


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    """The committed venue file, or an explicit empty state."""
    if not DATA_PATH.exists():
        return {"available": False, "venues": []}
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "venues": []}

    # Cleaned on the way IN, not only at fetch time. OpenStreetMap's
    # `opening_hours` is contributed free text and has already produced a real
    # person's phone number in it; a file written by an older version of the
    # fetch script, or edited by hand, must not be able to put that in front of
    # anybody. See `venue_rules`.
    return {
        "available": True,
        "venues": [clean_venue(v) for v in raw.get("venues", [])],
    }


def reload_venues() -> None:
    """Drop the cache. For tests, and for after a fetch."""
    _load.cache_clear()


def places_available() -> dict[str, Any]:
    """Whether real venue data is loaded, and how much.

    The client shows a fallback rather than an empty list when this is false,
    so the difference between "no venues match your filters" and "we have no
    venue data at all" stays visible.
    """
    state = _load()
    venues = state["venues"]
    return {
        "available": bool(state["available"] and venues),
        "count": len(venues),
        "with_hours": sum(1 for v in venues if v.get("opening_hours")),
        "source": "openstreetmap",
        "attribution": "© OpenStreetMap contributors",
        "note": (
            "Fetched once and committed; Spark has not evaluated these "
            "businesses. Run scripts/fetch_venues.py to populate."
        ),
    }


def search_places(
    interests: list[str],
    category: str | None = None,
    budget: str | None = None,
    energy: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Venues matching what the pair have in common.

    NOT GIVEN A LOCATION, and that is the point — see the invariant note at the
    top of this module. Ranking is on interest overlap and the structured
    attributes Date Studio already scores on.
    """
    state = _load()
    if not state["available"]:
        return {
            "available": False,
            "options": [],
            "detail": (
                "No venue data is loaded. Run `uv run python "
                "scripts/fetch_venues.py` to fetch it from OpenStreetMap. "
                "Nothing is invented in the meantime."
            ),
        }

    wanted = {i.lower() for i in interests}
    scored: list[tuple[int, dict]] = []
    for venue in state["venues"]:
        if category and venue.get("category") != category:
            continue
        if budget and budget != "flexible" and venue.get("budget") != budget:
            continue
        if energy and venue.get("energy") != energy:
            continue
        overlap = len(wanted & {t.lower() for t in venue.get("interests", ())})
        if overlap == 0:
            continue
        scored.append((overlap, venue))

    # Deterministic: overlap first, then id. A plan that reorders between takes
    # cannot be filmed twice.
    scored.sort(key=lambda pair: (-pair[0], pair[1]["venue_id"]))
    return {
        "available": True,
        "options": [venue for _, venue in scored[:limit]],
        "attribution": "© OpenStreetMap contributors",
    }


def travel_between(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> dict[str, Any]:
    """Straight-line distance turned into a walking estimate.

    Explicitly an ESTIMATE, and labelled as one everywhere it is shown. A real
    routing call would be another live dependency that can fail on stage, and
    for "is this a reasonable walk between two stops" the arithmetic answers
    the question the plan is actually asking.
    """
    # Equirectangular approximation. Over a few kilometres in Singapore the
    # error is metres, and the output is rounded to the nearest minute anyway.
    mean_lat = math.radians((from_lat + to_lat) / 2)
    x = math.radians(to_lon - from_lon) * math.cos(mean_lat)
    y = math.radians(to_lat - from_lat)
    metres = math.hypot(x, y) * 6371000

    minutes = max(1, round(metres / WALK_METRES_PER_MINUTE))
    return {
        "metres": round(metres),
        "minutes": minutes,
        "mode": "walking" if minutes <= 25 else "transit",
        "estimated": True,
        "detail": "Straight-line estimate, not a routed journey.",
    }


#: `Mo-Su 09:00-18:00`, `Tu-Su 10:00-19:00`, `24/7`, and a long tail this does
#: not attempt. Anything unparsed is UNKNOWN, never "open".
_HOURS = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def is_open_at(opening_hours: str | None, hour: int) -> dict[str, Any]:
    """Whether a venue is open, or whether we simply do not know.

    Three outcomes, and the third is the one that matters: OpenStreetMap's
    hours coverage is patchy, and treating "no data" as "open" is how a plan
    sends somebody to a locked door.
    """
    if not opening_hours:
        return {"state": "unknown", "detail": "Opening hours are not recorded."}
    if "24/7" in opening_hours:
        return {"state": "open", "detail": "Open 24 hours."}

    windows = _HOURS.findall(opening_hours)
    if not windows:
        return {
            "state": "unknown",
            "detail": f"Opening hours could not be read: {opening_hours!r}.",
        }
    for start_h, _start_m, end_h, _end_m in windows:
        if int(start_h) <= hour < int(end_h):
            return {"state": "open", "detail": f"Open {opening_hours}."}
    return {"state": "closed", "detail": f"Closed at this time ({opening_hours})."}


def maps_url(lat: float, lon: float, name: str = "") -> str:
    """A directions link that needs no API key.

    `google.com/maps/dir/?api=1` is a documented public URL. It opens the Google
    Maps app on a phone and the site on a desktop, with real directions to a
    real coordinate — the whole of the "Navigate" requirement, without a key, a
    billing account, or a credential that could leak.

    The coordinate is the destination, not the name: a name can be ambiguous
    and Maps may resolve it to the wrong branch, while a lat/lon cannot.
    """
    from urllib.parse import quote

    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={lat},{lon}"
        "&travelmode=walking"
    )
    if name:
        # Shown as the destination label where Maps supports it; the
        # coordinate above still decides where you are actually sent.
        url += f"&destination_place_id=&query={quote(name)}"
    return url
