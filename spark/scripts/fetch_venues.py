"""Fetch real venues from OpenStreetMap, once, into a committed file.

    uv run python scripts/fetch_venues.py

Writes `spark/data/venues_osm.json`. Everything downstream reads that file and
never calls the network, which is the point:

  IT CANNOT FAIL LIVE. A demo that queries Overpass on stage fails when the
  wifi does, or when a public server rate-limits you mid-take.

  IT IS DETERMINISTIC. The same venues every recording, so a re-take matches
  the one before it.

  IT WORKS OFFLINE. The Netlify build has no backend at all, and the mock
  adapter can be seeded from the same file.

  IT NEEDS NO KEY. No Google Cloud project, no billing, no credential to leak.

WHAT THIS IS HONEST ABOUT

OpenStreetMap is contributed data. Names and coordinates are good; opening
hours are patchy, and many venues have none. Where `opening_hours` is missing
this records `null` and the planner says "hours unknown" rather than asserting
a venue is open — inventing that is precisely how somebody ends up outside a
locked door.

These are REAL BUSINESSES that Spark has never visited or evaluated. Anything
built on this file must say where the data came from and must not imply
endorsement. Attribution is also a licence condition: any map view must carry
"© OpenStreetMap contributors".

Overpass is a free service run on donated hardware. This script is deliberately
a one-shot with a small bounding box and a polite pause between queries; do not
turn it into something that runs per request.

IT IS SAFE TO RUN AGAIN, AND OFTEN NECESSARY

Overpass returns 504 and 429 freely when it is busy, and a first run commonly
gets only some of the queries. So this MERGES into whatever is already in
`data/venues_osm.json` rather than replacing it: a second run tops up the
categories that failed and cannot lose the ones that worked. Overwriting was the
obvious way to write this and the wrong one — a re-run that happened to fail
more often than the first would silently shrink the file.

Each query is retried with a widening pause before it is given up on, and the
summary at the end says which categories are still empty, so "run it again" is a
decision based on what is missing rather than on hope.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcp.venue_rules import clean_opening_hours, interests_for  # noqa: E402

#: Overpass mirrors, tried in order. The main endpoint rate-limits hard when it
#: is busy; the others are the community mirrors that serve the same data, so a
#: 429 becomes "ask somewhere else" rather than "give up on this category".
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

#: NOT `overpass.osm.ch`. It serves a Switzerland-only extract, so a Singapore
#: bounding box comes back as a valid, empty answer — which looks like success
#: and silently reports "0 venues of that kind exist" rather than "ask
#: somewhere else". An empty result from a healthy-looking mirror is worse than
#: an error, because nothing retries it.

#: Attempts per query, across the mirrors. Small: this is a courtesy caller on
#: donated hardware, and hammering a busy server is how the whole IP gets a
#: longer ban than the one it is trying to wait out.
MAX_ATTEMPTS = 4

#: Seconds to wait after a failure, widening each time. A 429 means "you are
#: asking too fast", and answering it by asking again immediately is how a rate
#: limit becomes a block.
BACKOFF_SECONDS = (5, 20, 45)

#: Central Singapore. Deliberately small — a bigger box is a bigger burden on a
#: free service, and a date plan that spans the island is not a date plan.
BBOX = (1.26, 103.78, 1.36, 103.90)   # south, west, north, east

#: OSM tag -> the vocabulary Date Studio already scores on. Keeping the mapping
#: here means the rest of the system never learns what an `amenity=cafe` is.
#:
#: The interests a venue may claim live in `src/mcp/venue_rules.py`, keyed by
#: the tag recorded on each row — NOT by the coarse category. An earlier version
#: keyed them by category and gave a gym `chess`, which would have produced a
#: date plan claiming two people had both mentioned it.
QUERIES: tuple[tuple[str, str, str, str, str], ...] = (
    # (osm filter, category, format, energy, budget)
    ('["amenity"="cafe"]', "drink", "food", "low", "under_20"),
    ('["amenity"="restaurant"]', "food", "food", "low", "under_50"),
    ('["amenity"="fast_food"]', "food", "food", "low", "under_20"),
    ('["amenity"="bar"]', "drink", "food", "low", "under_50"),
    ('["tourism"="museum"]', "activity", "learning", "low", "under_20"),
    ('["tourism"="gallery"]', "activity", "learning", "low", "free"),
    ('["leisure"="park"]', "activity", "outdoors", "medium", "free"),
    ('["amenity"="marketplace"]', "food", "food", "low", "under_20"),
    ('["shop"="books"]', "activity", "activity", "low", "free"),
    ('["leisure"="fitness_centre"]', "activity", "activity", "high", "under_20"),
)

#: Interests the venue can plausibly serve, by category. The Date Agent needs a
#: tag overlap with what both people said, and OSM has no notion of "coffee" as
#: an interest — so the bridge is stated here rather than guessed at read time.
def osm_tag(filter_expr: str) -> str:
    """`["amenity"="cafe"]` -> `amenity=cafe`.

    Recorded on every venue so its interests can be looked up honestly later,
    and so a file can be re-cleaned without being re-fetched — which matters,
    because Overpass rate-limits hard enough that a re-fetch is not always
    available when you need one.
    """
    return filter_expr.replace('["', "").replace('"]', "").replace('"="', "=")


class _EmptyResult(RuntimeError):
    """A mirror answered, but with nothing. Treated as a miss, not an answer."""


def overpass(filter_expr: str) -> list[dict]:
    """One category, retried across the mirrors until something answers.

    Raises only after every attempt has failed, and the message says what
    actually went wrong rather than "request failed" — a 429 and a 504 call for
    different responses from the person running this (wait, versus try again
    now), so the distinction has to survive.
    """
    south, west, north, east = BBOX
    query = (
        f"[out:json][timeout:60];"
        f"(node{filter_expr}({south},{west},{north},{east});"
        f" way{filter_expr}({south},{west},{north},{east}););"
        f"out center tags 120;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()

    last_error = "no attempt was made"
    for attempt in range(MAX_ATTEMPTS):
        endpoint = OVERPASS_MIRRORS[attempt % len(OVERPASS_MIRRORS)]
        request = urllib.request.Request(
            endpoint,
            data=data,
            # Overpass asks for a real User-Agent so abuse can be traced to a
            # human.
            headers={
                "User-Agent": "spark-hackathon-demo/1.0 (one-shot venue fetch)"
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                elements = json.loads(response.read()).get("elements", [])
            if not elements:
                # A valid, empty answer is not necessarily the truth. A
                # region-limited mirror returns exactly this for a bounding box
                # it does not cover, and it looks like success — so it is
                # treated as a miss and another mirror is asked. Central
                # Singapore genuinely has cafes, restaurants and parks.
                last_error = "returned zero elements (wrong region, or busy)"
                if attempt < MAX_ATTEMPTS - 1:
                    raise _EmptyResult(last_error)
            return elements
        except _EmptyResult:
            pause = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            host = endpoint.split("/")[2]
            print(
                f"    {host} returned nothing; waiting {pause}s and trying "
                "another mirror",
                flush=True,
            )
            time.sleep(pause)
        except Exception as exc:                           # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS - 1:
                pause = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                host = endpoint.split("/")[2]
                print(
                    f"    {host} said {last_error}; waiting {pause}s and "
                    "trying another mirror",
                    flush=True,
                )
                time.sleep(pause)

    raise RuntimeError(
        f"all {MAX_ATTEMPTS} attempts failed, last: {last_error}. Overpass is "
        "a free service and rejects requests when it is busy — this is not a "
        "fault in the data. Run the script again later; it merges rather than "
        "replaces, so nothing already fetched is lost."
    )


def to_venue(
    element: dict, category: str, fmt: str, energy: str, budget: str, tag: str
) -> dict | None:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        # An unnamed node is useless in an itinerary — "go to the unnamed cafe"
        # is worse than no suggestion.
        return None

    lat = element.get("lat") or (element.get("center") or {}).get("lat")
    lon = element.get("lon") or (element.get("center") or {}).get("lon")
    if lat is None or lon is None:
        return None

    address = ", ".join(
        part
        for part in (
            " ".join(
                p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p
            ),
            tags.get("addr:postcode"),
        )
        if part
    ) or None

    return {
        "venue_id": f"osm-{element['type'][0]}{element['id']}",
        "name": name,
        "category": category,
        "format": fmt,
        "energy": energy,
        "budget": budget,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "address": address,
        # None means UNKNOWN, and the planner must render it as unknown. It
        # must never be treated as "open".
        #
        # Whitelisted rather than passed through: this field is contributed free
        # text, and a real fetch put a contributor's name and mobile number in
        # it. `venue_rules` keeps only recognisable syntax.
        "opening_hours": clean_opening_hours(tags.get("opening_hours")),
        "osm_tag": tag,
        "interests": list(interests_for(tag)),
        "source": "openstreetmap",
    }


def main() -> int:
    out_path = Path(__file__).resolve().parents[1] / "data" / "venues_osm.json"

    # Seed from whatever a previous run managed to get. Overpass fails often
    # enough that a first run rarely completes, and a re-run that replaced the
    # file could leave you with less than you started with.
    venues: dict[str, dict] = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            venues = {v["venue_id"]: v for v in existing.get("venues", [])}
            print(f"merging into {len(venues)} venues already fetched\n")
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            print(
                f"could not read the existing {out_path.name} ({exc}); "
                "starting fresh",
                file=sys.stderr,
            )

    started_with = len(venues)
    failed: list[str] = []

    for filter_expr, category, fmt, energy, budget in QUERIES:
        print(f"  fetching {filter_expr} ...", flush=True)
        try:
            elements = overpass(filter_expr)
        except Exception as exc:                       # noqa: BLE001
            print(f"    gave up: {exc}", file=sys.stderr)
            failed.append(filter_expr)
            continue
        added = 0
        for element in elements:
            venue = to_venue(
                element, category, fmt, energy, budget, osm_tag(filter_expr)
            )
            if venue and venue["venue_id"] not in venues:
                venues[venue["venue_id"]] = venue
                added += 1
        print(f"    +{added} ({len(venues)} total)")
        # Politeness. Overpass runs on donated hardware.
        time.sleep(2)

    if not venues:
        print(
            "No venues fetched. The planner will fall back to its "
            "'venue data unavailable' state, which is the correct behaviour — "
            "it will not invent places.",
            file=sys.stderr,
        )
        return 1

    with_hours = sum(1 for v in venues.values() if v["opening_hours"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "note": (
                    "Real venues from OpenStreetMap, fetched once and committed "
                    "so the demo never depends on a live API. Spark has not "
                    "visited or evaluated any of these businesses. Any map view "
                    "must show '(c) OpenStreetMap contributors'."
                ),
                "bbox": BBOX,
                "venues": sorted(venues.values(), key=lambda v: v["venue_id"]),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {len(venues)} venues -> {out_path}")
    if started_with:
        print(f"  {len(venues) - started_with} new this run")
    print(f"  with opening hours: {with_hours}  (the rest render as 'hours unknown')")

    # The planner needs an activity AND somewhere to sit or eat. Saying which
    # categories are thin is more useful than a total, because a run that
    # fetched 400 cafes and no activities cannot build a single itinerary.
    counts = Counter(v["category"] for v in venues.values())
    print("  by category: " + ", ".join(
        f"{name} {counts.get(name, 0)}" for name in ("activity", "food", "drink")
    ))
    missing = [name for name in ("activity", "food", "drink") if not counts.get(name)]
    if missing:
        print(
            f"\n  {', '.join(missing)} is empty, so no itinerary can be built "
            "yet. Run this again — it merges, so nothing is lost.",
            file=sys.stderr,
        )
    if failed:
        print(
            f"\n  {len(failed)} of {len(QUERIES)} queries were refused by "
            "Overpass and are missing from the file. Running this again later "
            "will top them up without re-fetching what worked.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
