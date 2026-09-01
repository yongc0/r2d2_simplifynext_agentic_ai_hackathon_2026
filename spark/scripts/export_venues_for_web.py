"""Bundle a slice of the fetched venues into the offline demo client.

    uv run python scripts/fetch_venues.py          # once, needs network
    uv run python scripts/export_venues_for_web.py # then this, no network

Writes `web/src/api/venues.generated.ts`.

WHY THE CLIENT NEEDS ITS OWN COPY

`MockAdapter` is what the recorded demo runs against and what the Netlify build
serves — there is no backend in either. Without a bundled copy the offline
client would have to either call the API (which is not there) or invent a venue
(which is the one thing the whole design refuses to do), so it would show the
"no venue data" state forever.

WHY IT IS GENERATED RATHER THAN WRITTEN

So nobody can accidentally type a plausible address into it. Every row here came
from OpenStreetMap via the fetch script; nothing in this file is authored.

WHAT IS DELIBERATELY DROPPED

Venues with no name, and venues outside the three categories the planner uses.

`opening_hours` is passed through `venue_rules.clean_opening_hours`, which keeps
only recognisable opening-hours syntax and turns everything else into `null` —
rendered as UNKNOWN, never as open. That whitelist is not fussiness: the real
fetch contained a contributor's name and mobile number in that field, and this
file goes into a public repository and a JavaScript bundle.

Interests are re-derived rather than trusted, for the same reason: an earlier
mapping tagged a 24-hour gym with `chess`, which would have produced a plan
claiming two people bonded over it.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcp.venue_rules import clean_venue  # noqa: E402

#: How many of each category to bundle. Small on purpose: this ships in a
#: JavaScript bundle, and a date planner does not improve with a thousand cafes.
PER_CATEGORY = 25

CATEGORIES = ("activity", "food", "drink")

HEADER = '''/**
 * GENERATED FILE — do not edit by hand.
 *
 * Written by `spark/scripts/export_venues_for_web.py` from
 * `spark/data/venues_osm.json`, which `spark/scripts/fetch_venues.py` fetches
 * once from OpenStreetMap.
 *
 * It is generated rather than hand-written for one reason: nobody can
 * accidentally type a plausible address into a generated file. Every venue here
 * is a real place somebody contributed to OpenStreetMap, and Spark has visited
 * and evaluated none of them.
 *
 * THE LIST BELOW IS EMPTY UNTIL THOSE TWO SCRIPTS HAVE RUN, and empty is a
 * legitimate state: the offline demo then shows "we cannot name places yet"
 * rather than inventing somewhere to go.
 *
 *   cd spark
 *   uv run python scripts/fetch_venues.py
 *   uv run python scripts/export_venues_for_web.py
 *
 * Licence: any surface rendering these venues must show
 * "© OpenStreetMap contributors".
 */

export interface MockVenue {
  venueId: string;
  name: string;
  category: "activity" | "food" | "drink";
  budget: string;
  energy: string;
  lat: number;
  lon: number;
  /** `null` when OpenStreetMap has no address for it. Never a guess. */
  address: string | null;
  /** `null` means UNKNOWN. It must never be rendered as "open". */
  openingHours: string | null;
  interests: string[];
}

export const GENERATED_VENUES: MockVenue[] = '''


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = root / "data" / "venues_osm.json"
    target = root.parent / "web" / "src" / "api" / "venues.generated.ts"

    if not source.exists():
        print(
            f"{source} does not exist. Run `uv run python scripts/fetch_venues.py` "
            "first — it fetches the venues from OpenStreetMap. Nothing is "
            "invented in the meantime, so the client will keep showing its "
            "'no venue data' state until you do.",
            file=sys.stderr,
        )
        return 1

    # Cleaned before anything is chosen, so the "prefer venues with hours"
    # sort below ranks on hours that survived the whitelist rather than on free
    # text that merely looked like some.
    venues = [
        clean_venue(v)
        for v in json.loads(source.read_text(encoding="utf-8"))["venues"]
    ]

    chosen: list[dict] = []
    for category in CATEGORIES:
        matching = [v for v in venues if v.get("category") == category]
        # Sorted by id, so the bundle is byte-identical across runs and a
        # regenerated file does not show up as a diff full of reordering.
        matching.sort(key=lambda v: v["venue_id"])
        # Venues WITH hours first: the planner can reason about those, and a
        # demo in which every stop says "hours unknown" reads as broken even
        # though it is being honest.
        matching.sort(key=lambda v: v.get("opening_hours") is None)
        chosen.extend(matching[:PER_CATEGORY])

    # A venue that can claim no interest can never be grounded in one, so it
    # would never be suggested. Bundling it would only pad the file.
    chosen = [v for v in chosen if v["interests"]]

    rows = [
        {
            "venueId": v["venue_id"],
            "name": v["name"],
            "category": v["category"],
            "budget": v["budget"],
            "energy": v["energy"],
            "lat": v["lat"],
            "lon": v["lon"],
            "address": v.get("address"),
            "openingHours": v.get("opening_hours"),
            "interests": v.get("interests", []),
        }
        for v in chosen
    ]

    body = json.dumps(rows, indent=2, ensure_ascii=False)
    stamp = datetime.now(UTC).date().isoformat()
    target.write_text(
        f"{HEADER}{body};\n\n"
        "/** Written by the export script so the interface can say how fresh "
        "this is. */\n"
        f'export const GENERATED_AT: string | null = "{stamp}";\n',
        encoding="utf-8",
    )

    with_hours = sum(1 for r in rows if r["openingHours"])
    print(f"wrote {len(rows)} venues -> {target}")
    print(f"  with opening hours: {with_hours}  (the rest render as 'hours unknown')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
