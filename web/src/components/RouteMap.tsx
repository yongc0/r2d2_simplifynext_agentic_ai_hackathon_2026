import type { ItineraryStop } from "../api/types";

/**
 * The route, as numbered markers joined in order.
 *
 * WHY THIS IS DRAWN RATHER THAN TILED
 *
 * A slippy map needs tiles, and tiles need the network. Everything else in this
 * client works offline — that is what makes the demo filmable in a room with
 * bad wifi and what makes the Netlify build work with no backend at all — and a
 * map that goes grey on the one screen the whole feature is about would undo
 * that. So the coordinates are projected and drawn: no tile server, no API key,
 * no request, nothing to fail.
 *
 * It is honest about what it is. This shows the ORDER and the RELATIVE POSITION
 * of the stops, which is what "stop 2 is a short walk north of stop 1" needs.
 * It is not a street map and does not pretend to be one, and the thing a person
 * actually needs — turn-by-turn directions to a real address — is one tap away
 * on every stop, in the map application they already use.
 *
 * WHY THERE IS NO GOOGLE MAPS EMBED
 *
 * Every embeddable Google Maps product needs a browser key, and a browser key
 * is in the bundle, which is the one thing the requirement explicitly forbids.
 * Proxying tiles through our own backend would keep the key server-side but the
 * backend does not exist in the offline build. The `Navigate` links do use
 * Google Maps — via `maps/dir/?api=1`, a documented public URL that needs no
 * key at all — so the person gets real Google directions without Spark ever
 * holding a credential.
 *
 * ATTRIBUTION IS NOT OPTIONAL. The coordinates are OpenStreetMap's, and the
 * licence requires the credit that is rendered below the map.
 */
export function RouteMap({
  stops,
  attribution,
  activeStopId,
  onSelectStop,
}: {
  stops: ItineraryStop[];
  attribution: string;
  activeStopId?: string | null;
  onSelectStop?: (stopId: string) => void;
}) {
  if (stops.length === 0) return null;

  const points = project(stops);

  return (
    <figure className="m-0">
      <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#11151c]">
        <svg
          viewBox="0 0 100 68"
          className="block h-44 w-full sm:h-56"
          role="img"
          aria-label={`Route with ${stops.length} stops, in order: ${stops
            .map((s) => `${s.order}, ${s.venueName}`)
            .join("; ")}`}
        >
          {/* A faint grid, so the drawing reads as a plan rather than as a
              photograph of a street map it is not. */}
          <defs>
            <pattern id="route-grid" width="10" height="10" patternUnits="userSpaceOnUse">
              <path
                d="M 10 0 L 0 0 0 10"
                fill="none"
                stroke="rgba(255,255,255,0.05)"
                strokeWidth="0.4"
              />
            </pattern>
          </defs>
          <rect width="100" height="68" fill="url(#route-grid)" />

          {points.length > 1 ? (
            <polyline
              points={points.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="rgba(255,138,101,0.55)"
              strokeWidth="1.2"
              strokeDasharray="3 2"
              strokeLinecap="round"
            />
          ) : null}

          {points.map((point, index) => {
            const stop = stops[index];
            const active = activeStopId === stop.stopId;
            return (
              <g
                key={stop.stopId}
                onClick={onSelectStop ? () => onSelectStop(stop.stopId) : undefined}
                className={onSelectStop ? "cursor-pointer" : undefined}
              >
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={active ? 5 : 4}
                  fill={active ? "#ff8a65" : "#1c232e"}
                  stroke="#ff8a65"
                  strokeWidth="1"
                />
                <text
                  x={point.x}
                  y={point.y + 1.5}
                  textAnchor="middle"
                  fontSize="4"
                  fill={active ? "#11151c" : "#ff8a65"}
                  fontWeight="600"
                >
                  {stop.order}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <figcaption className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[10px] text-muted">
        <span>Relative positions and order, not a street map.</span>
        <span>{attribution}</span>
      </figcaption>
    </figure>
  );
}

/**
 * Latitude and longitude onto the viewBox, with the aspect ratio kept.
 *
 * The two axes are scaled by the SAME factor. Stretching each to fill the box
 * independently would be the easy version and would misrepresent the walk: two
 * stops a minute apart would be drawn as far apart as two stops a mile apart,
 * on an image whose whole job is to show how far apart things are.
 *
 * A single stop, or several at one point, lands in the middle rather than
 * dividing by a zero-width range.
 */
function project(stops: ItineraryStop[]): { x: number; y: number }[] {
  const lats = stops.map((s) => s.lat);
  const lons = stops.map((s) => s.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  // Longitude degrees are shorter than latitude degrees away from the equator.
  const latScale = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  const spanLat = maxLat - minLat;
  const spanLon = (maxLon - minLon) * latScale;
  const span = Math.max(spanLat, spanLon);

  if (span === 0) {
    return stops.map(() => ({ x: 50, y: 34 }));
  }

  const padding = 14;
  const usable = 100 - padding * 2;
  const scale = usable / span;

  return stops.map((stop) => ({
    x: 50 + ((stop.lon - (minLon + maxLon) / 2) * latScale * scale),
    // SVG y grows downward; north should be up.
    y: 34 - ((stop.lat - (minLat + maxLat) / 2) * scale),
  }));
}
