/**
 * The seam between the client's vocabulary and the backend's.
 *
 * FRONTEND.md §4 and `spark/src/schemas/` disagree in four places. Rather than
 * silently picking a winner in a dozen components, every difference is resolved
 * here, once, with the reasoning attached. Overriding any of these decisions is
 * a change to this file and nothing else.
 *
 * ---------------------------------------------------------------------------
 * 1. Intent values — RESOLVED IN FAVOUR OF THE BACKEND.
 *
 *    FRONTEND.md wrote `partner_long` / `partner_short`; the pydantic enum is
 *    `partner_long_term` / `partner_short_term`. That is a straight mismatch
 *    with no upside — HttpAdapter would fail to match and the failure would be
 *    silent. The backend values win because they are the ones on the wire.
 *
 * 2. EncounterState — DELIBERATELY TWO TYPES.
 *
 *    The backend machine has 13 states; the client needs 10, and only 8 are
 *    shared. `PROFILED`, `POOLED` and `SELECTED` are backend-internal — the
 *    user sees nothing at all until `NOTIFIED`, and surfacing them would leak
 *    that a selection is in progress. `LOCKED_IN` and `RELEASED` belong to the
 *    LockIn object, not the encounter. `IDLE` and `WINDOW_OPEN` are client-only
 *    UI states with no backend counterpart.
 *
 *    Merging them would either leak internals into the UI or lose the two
 *    states the UI genuinely needs, so they stay separate with one mapping.
 *
 * 3. The pseudonymous handle — SHOWN PRE-REVEAL, behind SHOW_HANDLE_PRE_REVEAL.
 *
 *    A handle like "azure-heron" is not an identity: it is assigned from a word
 *    list and is never derived from a name (`spark/src/ids.py`). Invariant 9.2
 *    forbids "name, photo, age, blurred silhouette, initial" — a handle is none
 *    of those. It gives two strangers something to refer to for three minutes
 *    and reinforces that this is deliberately not a name.
 *
 *    Flip the flag to false and the handle disappears everywhere.
 *
 * 4. RevealedPerson / ContinuityBrief — CLIENT SHAPES.
 *
 *    `avatarSeed` and `sharedInterests` have no backend counterpart on
 *    `RevealView`, and `ContinuityBrief`'s fields are named differently from
 *    `LockInBrief`. These are presentation concerns; the mappings live below.
 */

import type { ClientState, Intent } from "./types";

/**
 * Show the pseudonymous handle before a mutual reveal.
 *
 * See note 3 above. This is the whole switch — one line, one place.
 */
export const SHOW_HANDLE_PRE_REVEAL = true;

/** Intent, exactly as `spark/src/schemas/core.py` spells it. */
export const WIRE_INTENTS = [
  "partner_long_term",
  "partner_short_term",
  "friends",
] as const;

/** The backend's `EncounterState`, verbatim. Do not edit without editing the
 *  pydantic enum — `spark/tests/test_wire_contract.py` fails if they drift. */
export const WIRE_ENCOUNTER_STATES = [
  "PROFILED",
  "POOLED",
  "SELECTED",
  "NOTIFIED",
  "PENDING_ACCEPT",
  "CONNECTED",
  "CALL_ENDED",
  "PENDING_CONSENT",
  "REVEALED",
  "CLOSED",
  "ABANDONED",
  "LOCKED_IN",
  "RELEASED",
] as const;

export type WireEncounterState = (typeof WIRE_ENCOUNTER_STATES)[number];

/**
 * Backend state -> what the client should be showing.
 *
 * The three backend-internal states collapse to `WINDOW_OPEN`: from the user's
 * side, "we are choosing" and "the window is open" are the same experience, and
 * they must be, or the UI would betray that a selection had been made before
 * the notification arrives.
 */
export function mapWireState(state: WireEncounterState): ClientState {
  switch (state) {
    case "PROFILED":
    case "POOLED":
    case "SELECTED":
      return "WINDOW_OPEN";
    case "NOTIFIED":
      return "NOTIFIED";
    case "PENDING_ACCEPT":
      return "PENDING_ACCEPT";
    case "CONNECTED":
      return "CONNECTED";
    case "CALL_ENDED":
      return "CALL_ENDED";
    case "PENDING_CONSENT":
      return "PENDING_CONSENT";
    case "REVEALED":
    case "LOCKED_IN":
      return "REVEALED";
    case "CLOSED":
      return "CLOSED";
    // A released lock-in is not a live encounter; the client is idle again.
    case "RELEASED":
      return "IDLE";
    case "ABANDONED":
      return "ABANDONED";
  }
}

/**
 * A coarse time bucket, rendered into words.
 *
 * This is where invariant 1 is actually satisfied. The backend hands over
 * `shared_bucket: TimeBucket` — an enum, never a place and never a time — and
 * the only thing the client is permitted to do with it is turn it into a
 * phrase. There is deliberately no branch here that produces a location.
 */
const BUCKET_PHRASES: Record<string, string> = {
  early_morning: "Your paths crossed early this morning",
  morning: "Your paths crossed this morning",
  midday: "Your paths crossed around midday",
  afternoon: "Your paths crossed this afternoon",
  evening: "Your paths crossed this evening",
  night: "Your paths crossed late tonight",
};

export function overlapHintFor(bucket: string | null | undefined): string {
  if (!bucket) return "Your paths crossed today";
  return BUCKET_PHRASES[bucket] ?? "Your paths crossed today";
}

/** Intent, rendered for a person. British spelling, per CLAUDE.md. */
/**
 * A label back to the value the backend stores.
 *
 * The inverse of `intentLabel`, kept beside it so the two cannot drift. The
 * profile screen edits labels and the API takes values, and deriving one from
 * the other at a call site would put this mapping in two places.
 */
export function intentValue(label: string): string {
  const match = (
    ["partner_long_term", "partner_short_term", "friends"] as const
  ).find((value) => intentLabel(value) === label);
  if (!match) {
    // Actionable rather than a silent fallback: a label with no value means
    // the two lists have drifted, and defaulting would quietly change what
    // somebody is looking for.
    throw new Error(
      `no connection intent matches the label ${label} — intentLabel and ` +
        "intentValue have drifted apart",
    );
  }
  return match;
}

export function intentLabel(intent: Intent): string {
  switch (intent) {
    case "partner_long_term":
      return "Something long term";
    case "partner_short_term":
      return "Something short term";
    case "friends":
      return "Friends";
  }
}
