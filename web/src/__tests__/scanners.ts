/**
 * Invariant scanners — the client-side counterpart of
 * `spark/src/safety/guardrails.py`.
 *
 * Deliberately the same approach as the Python guardrail: scan what was
 * ACTUALLY rendered, not what we intended to render. A front end breaks these
 * by accident — a placeholder reading "2 km away" undoes the whole safety
 * argument and would ship looking like copy.
 *
 * Kept out of the test files so both `invariants.test.tsx` and `mock.test.ts`
 * can use them without one file's `todo`s being counted twice.
 */

// ---------------------------------------------------------------------------
// The scanners
// ---------------------------------------------------------------------------

/**
 * INVARIANT 1 — never render a distance, coordinate, place name, or map.
 *
 * Written out one per line so adding a case is a one-line diff and a reviewer
 * can see exactly what is forbidden.
 */
const LOCATION_PATTERNS: [RegExp, string][] = [
  [/\b\d+(?:\.\d+)?\s*(?:m|km|metres?|meters?|miles?|mi)\b/i, "states a distance"],
  [/\b\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b/, "contains coordinates"],
  [/\b(?:lat|latitude|lon|lng|longitude)\b/i, "names a coordinate field"],
  [/\bnear(?:by|\s+you|\s+your)\b/i, "implies proximity"],
  [/\b(?:just )?around the corner\b/i, "implies proximity"],
  [/\bwalking distance\b/i, "implies proximity"],
  [/\b\d+\s*min(?:ute)?s?\s+(?:away|from you)\b/i, "states a travel time"],
  [/\bsame (?:building|block|street|office|floor|mrt|station)\b/i, "names a place"],
  [/\bcurrently (?:at|in|near)\b/i, "implies live location"],
  [/\bcell[_ ]?id\b/i, "exposes the overlap cell"],
];

/** Place names that exist in the simulated world (`spark/src/sim/world.py`).
 *  They are listed here so the scanner can FORBID them. */
const PLACE_NAMES = [
  "Raffles Place", "Tanjong Pagar", "Bugis", "Jurong East", "Tampines",
  "Woodlands", "Serangoon", "Clementi", "Novena", "Paya Lebar",
  "Queenstown", "Bishan", "Yishun", "Punggol", "Dhoby Ghaut",
  "Outram Park", "Kallang", "Redhill", "Toa Payoh", "Buona Vista",
];

export function scanForLocation(text: string): string[] {
  const found: string[] = [];
  for (const [pattern, why] of LOCATION_PATTERNS) {
    if (pattern.test(text)) found.push(why);
  }
  for (const place of PLACE_NAMES) {
    if (new RegExp(`\\b${place}\\b`, "i").test(text)) {
      found.push(`names the place "${place}"`);
    }
  }
  return found;
}

/**
 * INVARIANT 2 — never render identity before mutual consent.
 *
 * Field-name based, because the realistic failure is a component spreading a
 * richer object into a pre-reveal view, not someone typing a name in by hand.
 */
export const FORBIDDEN_PRE_REVEAL_FIELDS = [
  "name", "displayName", "display_name", "firstName", "lastName",
  "age", "photo", "photoUrl", "picture", "image", "imageUrl",
  "avatar", "avatarUrl", "initial", "initials", "silhouette",
  "phone", "number", "email",
];

export function scanForIdentityFields(value: unknown): string[] {
  const found: string[] = [];
  const walk = (node: unknown) => {
    if (node === null || typeof node !== "object") return;
    if (Array.isArray(node)) return node.forEach(walk);
    for (const [key, child] of Object.entries(node)) {
      if (FORBIDDEN_PRE_REVEAL_FIELDS.includes(key)) found.push(key);
      walk(child);
    }
  };
  walk(value);
  return found;
}
