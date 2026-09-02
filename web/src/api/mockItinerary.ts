/**
 * The offline date planner — the same rules as the backend, in the browser.
 *
 * `MockAdapter` is what the demo is filmed against, so this has to produce the
 * same kind of plan the server does: real venues, clock times, walking legs,
 * and the three opening states. A demo that showed a nicer itinerary than the
 * product can build would be a lie told at 24 frames a second.
 *
 * WHERE THE VENUES COME FROM
 *
 * `venues.generated.ts`, written by `spark/scripts/export_venues_for_web.py`
 * from the same OpenStreetMap fetch the backend reads. It is generated rather
 * than hand-written for one reason: nobody can accidentally type a plausible
 * address into it.
 *
 * IF IT HAS NOT BEEN GENERATED the list is empty, and every caller reports the
 * unavailable state instead of planning. The offline demo must not be the one
 * place in the system that invents a place — see `MOCK_VENUES`.
 */

import type {
  DatePreferences,
  Itinerary,
  ItineraryResult,
  ItineraryStop,
  TravelLeg,
} from "./types";
import { GENERATED_VENUES, type MockVenue } from "./venues.generated";

export type { MockVenue };

/** Evidence and shape selected by the abstract plan the person clicked. */
export interface MockItineraryContext {
  groundedIn: string[];
  preferredEnergies: string[];
  preferredDuration?: string;
  preferredFormat?: string;
}

/**
 * The venues the offline demo can plan with. Empty until the export script has
 * run, and empty is a legitimate state that every caller handles.
 */
export const MOCK_VENUES: MockVenue[] = GENERATED_VENUES;

/** Matches `WALK_METRES_PER_MINUTE` in `spark/src/mcp/places.py`. */
const WALK_METRES_PER_MINUTE = 78;

const BUCKET_START_HOUR: Record<string, number> = {
  early_morning: 7,
  morning: 9,
  midday: 12,
  afternoon: 15,
  evening: 18,
  night: 21,
};

const COST_TEXT: Record<string, string> = {
  free: "Free",
  under_20: "Around $10-20 each",
  under_50: "Around $20-50 each",
  flexible: "Varies",
};

const DAY_LABEL: Record<string, string> = {
  early_morning: "An early start",
  morning: "A morning",
  midday: "Lunchtime",
  afternoon: "An afternoon",
  evening: "An evening",
  night: "A late one",
};

/** Straight-line distance in metres. Equirectangular; the error over a few
 *  kilometres is metres, and the answer is rounded to a minute anyway. */
function metresBetween(
  fromLat: number,
  fromLon: number,
  toLat: number,
  toLon: number,
): number {
  const meanLat = ((fromLat + toLat) / 2) * (Math.PI / 180);
  const x = (toLon - fromLon) * (Math.PI / 180) * Math.cos(meanLat);
  const y = (toLat - fromLat) * (Math.PI / 180);
  return Math.hypot(x, y) * 6371000;
}

function travelLeg(from: ItineraryStop, to: MockVenue): TravelLeg {
  const metres = metresBetween(from.lat, from.lon, to.lat, to.lon);
  const minutes = Math.max(1, Math.round(metres / WALK_METRES_PER_MINUTE));
  return {
    minutes,
    metres: Math.round(metres),
    mode: minutes <= 25 ? "walking" : "transit",
    estimated: true,
    detail: "Straight-line estimate, not a routed journey.",
  };
}

/**
 * open / closed / unknown, at an hour.
 *
 * Three outcomes, and the third is the one that matters. A venue with no
 * recorded hours is UNKNOWN and is rendered as unknown; treating missing data
 * as "open" is how a plan sends two people to a locked door.
 */
export function openingStateAt(
  openingHours: string | null,
  hour: number,
): { state: "open" | "closed" | "unknown"; detail: string } {
  if (!openingHours) {
    return { state: "unknown", detail: "Opening hours are not recorded." };
  }
  if (openingHours.includes("24/7")) {
    return { state: "open", detail: "Open 24 hours." };
  }
  const windows = [...openingHours.matchAll(/(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/g)];
  if (windows.length === 0) {
    return {
      state: "unknown",
      detail: `Opening hours could not be read: ${openingHours}.`,
    };
  }
  for (const window of windows) {
    if (Number(window[1]) <= hour && hour < Number(window[3])) {
      return { state: "open", detail: `Open ${openingHours}.` };
    }
  }
  return { state: "closed", detail: `Closed at this time (${openingHours}).` };
}

function clock(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function toMinutes(value: string): number {
  const [h, m] = value.split(":");
  return Number(h) * 60 + Number(m);
}

/** The keyless directions link, identical to `places.maps_url`. */
export function mapsUrl(lat: number, lon: number): string {
  return (
    "https://www.google.com/maps/dir/?api=1" +
    `&destination=${lat},${lon}` +
    "&travelmode=walking"
  );
}

/**
 * Eligible venues ranked by shared-interest fit, then by plan preference.
 *
 * The first stop must overlap the interest that grounded the selected plan.
 * Later stops use proximity as a tie-breaker so the result is an itinerary,
 * not two individually sensible venues ten kilometres apart.
 *
 * This is venue-to-venue distance between stops already chosen for a plan, not
 * proximity to a person — nothing here knows where either participant is or has
 * been. Squared coordinate delta is enough: it is monotonic with real distance
 * at this scale, and only the chosen venue's leg gets measured properly.
 */
function candidates(
  categories: MockVenue["category"][],
  budget: string | null | undefined,
  used: Set<string>,
  previous: ItineraryStop | null = null,
  interests: string[] = [],
  preferredEnergies: string[] = [],
  preferredFormat?: string,
): MockVenue[] {
  const eligible = MOCK_VENUES.filter(
    (venue) =>
      categories.includes(venue.category) &&
      !used.has(venue.venueId) &&
      (!budget || budget === "flexible" || venue.budget === budget) &&
      (interests.length === 0 ||
        venue.interests.some((interest) => interests.includes(interest))),
  );

  const fit = (venue: MockVenue) => {
    const interestHits = venue.interests.filter((interest) =>
      interests.includes(interest),
    ).length;
    const energyHit = preferredEnergies.includes(venue.energy) ? 1 : 0;
    const categoryHit =
      preferredFormat === "food"
        ? venue.category === "food" || venue.category === "drink"
        : preferredFormat
          ? venue.category === "activity"
          : false;
    // Shared interest is the hard filter above and the strongest ordering
    // signal here. Energy and the chosen plan shape break genuine-fit ties.
    return interestHits * 100 + energyHit * 10 + (categoryHit ? 3 : 0);
  };

  return eligible.sort((a, b) => {
    const byFit = fit(b) - fit(a);
    if (byFit) return byFit;
    if (!previous) return a.venueId.localeCompare(b.venueId);
    const gap = (v: MockVenue) =>
      (previous.lat - v.lat) ** 2 + (previous.lon - v.lon) ** 2;
    return gap(a) - gap(b) || a.venueId.localeCompare(b.venueId);
  });
}

function buildStop(
  venue: MockVenue,
  order: number,
  startMinutes: number,
  durationMinutes: number,
  travel: TravelLeg | null,
  groundedIn: string[],
): ItineraryStop {
  const opening = openingStateAt(venue.openingHours, Math.floor(startMinutes / 60) % 24);
  const shared = venue.interests.filter((i) => groundedIn.includes(i));
  const kind =
    venue.category === "activity"
      ? "something to do"
      : venue.category === "food"
        ? "somewhere to eat afterwards"
        : "somewhere to sit and talk";
  return {
    stopId: `stop-${venue.venueId}-${order}`,
    order,
    activityType: venue.category,
    venueId: venue.venueId,
    venueName: venue.name,
    address: venue.address,
    lat: venue.lat,
    lon: venue.lon,
    startTime: clock(startMinutes),
    endTime: clock(startMinutes + durationMinutes),
    durationMinutes,
    estimatedCost: COST_TEXT[venue.budget] ?? "Varies",
    costBand: venue.budget,
    rationale: shared.length
      ? `You have both mentioned ${shared.slice(0, 2).join(" and ")}, and this is ${kind}.`
      : `Chosen as ${kind} that fits the shape of the evening.`,
    travelFromPrevious: travel,
    mapsUrl: mapsUrl(venue.lat, venue.lon),
    openingState: opening.state,
    openingHours: venue.openingHours,
    openingDetail: opening.detail,
    isCommercialPartner: false,
  };
}

/** The stops an itinerary totals up to, including the walks between. */
function totals(stops: ItineraryStop[]): { minutes: number; cost: string } {
  const minutes = stops.reduce(
    (sum, stop) => sum + stop.durationMinutes + (stop.travelFromPrevious?.minutes ?? 0),
    0,
  );
  const bands = new Set(stops.map((s) => s.costBand));
  const cost =
    bands.size === 1 && bands.has("free")
      ? "Free"
      : bands.has("under_50") || bands.has("flexible")
        ? "Roughly $20-50 each, depending on where you stop"
        : "Roughly $10-20 each";
  return { minutes, cost };
}

/** A hop longer than this is two outings with a commute between them. */
const COMFORTABLE_LEG_MINUTES = 25;

function noteFor(stops: ItineraryStop[], skippedClosed: number): string {
  const notes: string[] = [];
  const longest = Math.max(
    0,
    ...stops.map((s) => s.travelFromPrevious?.minutes ?? 0),
  );
  if (longest > COMFORTABLE_LEG_MINUTES) {
    notes.push(
      `There is a ${longest}-minute journey between stops — the closest ` +
        "option of that kind was some way off.",
    );
  }
  const unknown = stops.filter((s) => s.openingState === "unknown");
  if (unknown.length > 0) {
    notes.push(
      `Opening hours are not recorded for ${unknown
        .slice(0, 3)
        .map((s) => s.venueName)
        .join(", ")} — worth checking before you go.`,
    );
  }
  if (skippedClosed > 0) {
    notes.push(`${skippedClosed} option(s) were shut at that hour and were left out.`);
  }
  return notes.join(" ");
}

/**
 * One evening grounded in the selected path, then somewhere nearby if time
 * permits.
 *
 * Deterministic — fit, preferences, proximity and id form a stable ordering,
 * so the same request gives the same plan on every take.
 */
export function buildMockItinerary(
  lockInId: string,
  preferences: Partial<DatePreferences> & { pathId?: string },
  existing: Map<string, Itinerary>,
  context: MockItineraryContext,
): ItineraryResult {
  const bucket = preferences.timeBucket ?? "evening";
  const groundedIn = [...new Set(context.groundedIn.map((item) => item.toLowerCase()))];
  if (groundedIn.length === 0) {
    return {
      itinerary: null,
      reason: "Nothing you have both mentioned to build this plan on yet.",
      dataUnavailable: false,
    };
  }
  const used = new Set<string>(
    // Never re-offer a venue this connection already has a plan around.
    [...existing.values()]
      .filter((it) => it.lockInId === lockInId)
      .flatMap((it) => it.stops.map((s) => s.venueId)),
  );

  let cursor = (BUCKET_START_HOUR[bucket] ?? 18) * 60;
  const stops: ItineraryStop[] = [];
  let skippedClosed = 0;

  const durationBand = context.preferredDuration ?? "two_hours";
  const durations =
    durationBand === "one_hour"
      ? [60]
      : durationBand === "whole_evening"
        ? [90, 75]
        : [70, 50];

  for (const [index, duration] of durations.entries()) {
    const previous = stops[stops.length - 1] ?? null;
    let placed = false;

    for (const venue of candidates(
      index === 0 ? ["activity", "drink", "food"] : ["food", "drink"],
      preferences.budget,
      used,
      previous,
      index === 0 ? groundedIn : [],
      context.preferredEnergies,
      context.preferredFormat,
    )) {
      const travel = previous ? travelLeg(previous, venue) : null;
      const arrive = cursor + (travel?.minutes ?? 0);
      if (openingStateAt(venue.openingHours, Math.floor(arrive / 60) % 24).state === "closed") {
        skippedClosed += 1;
        continue;
      }
      const stop = buildStop(venue, stops.length + 1, arrive, duration, travel, groundedIn);
      stops.push(stop);
      used.add(venue.venueId);
      cursor = arrive + duration;
      placed = true;
      break;
    }
    if (!placed && index === 0) break;
  }

  if (stops.length === 0) {
    return {
      itinerary: null,
      reason:
        "Nothing that fits is open at that time. Try another part of the day, " +
        "or relax one of the boxes.",
      dataUnavailable: false,
    };
  }

  const { minutes, cost } = totals(stops);
  const now = new Date().toISOString();
  return {
    itinerary: {
      itineraryId: `itin-${lockInId}-${existing.size + 1}`,
      lockInId,
      pathId: preferences.pathId ?? `${lockInId}-easy`,
      headline: stops.map((s) => s.venueName).join(", then "),
      timeBucket: bucket,
      dayLabel: DAY_LABEL[bucket] ?? "An evening",
      stops,
      totalDurationMinutes: minutes,
      totalCostEstimate: cost,
      groundedIn,
      status: "draft",
      note: noteFor(stops, skippedClosed),
      attribution: "© OpenStreetMap contributors",
      updatedAt: now,
      hasReflection: false,
    },
    reason: "",
    dataUnavailable: false,
  };
}

/**
 * Swap ONE stop for a different venue of the same kind, and re-time it.
 *
 * The stops before it are untouched — same venues, same times. The one being
 * replaced moves, because a different venue is a different walk.
 *
 * Returns `null` when there is no alternative, so the caller can hand back the
 * plan the person already had rather than destroying it.
 */
export function replaceMockStop(
  itinerary: Itinerary,
  order: number,
): Itinerary | null {
  const index = order - 1;
  const target = itinerary.stops[index];
  if (!target) return null;
  const used = new Set(itinerary.stops.map((s) => s.venueId));
  const previous = itinerary.stops[index - 1] ?? null;
  const from = previous ? toMinutes(previous.endTime) : toMinutes(target.startTime);

  for (const venue of candidates(
    [target.activityType],
    undefined,
    used,
    previous,
    target.order === 1 ? itinerary.groundedIn : [],
  )) {
    const travel = previous ? travelLeg(previous, venue) : null;
    const arrive = from + (travel?.minutes ?? 0);
    if (openingStateAt(venue.openingHours, Math.floor(arrive / 60) % 24).state === "closed") {
      continue;
    }
    const stops = [...itinerary.stops];
    stops[index] = buildStop(
      venue,
      target.order,
      arrive,
      target.durationMinutes,
      travel,
      itinerary.groundedIn,
    );
    // Everything after the swap is re-timed off the new end. A plan whose
    // later times did not move would be a schedule that no longer adds up.
    let cursor = toMinutes(stops[index].endTime);
    for (let i = index + 1; i < stops.length; i += 1) {
      const leg = travelLeg(stops[i - 1], {
        lat: stops[i].lat,
        lon: stops[i].lon,
      } as MockVenue);
      const arriveNext = cursor + leg.minutes;
      stops[i] = {
        ...stops[i],
        travelFromPrevious: leg,
        startTime: clock(arriveNext),
        endTime: clock(arriveNext + stops[i].durationMinutes),
      };
      cursor = arriveNext + stops[i].durationMinutes;
    }
    const { minutes, cost } = totals(stops);
    return {
      ...itinerary,
      stops,
      totalDurationMinutes: minutes,
      totalCostEstimate: cost,
      note: noteFor(stops, 0),
      updatedAt: new Date().toISOString(),
    };
  }
  return null;
}
