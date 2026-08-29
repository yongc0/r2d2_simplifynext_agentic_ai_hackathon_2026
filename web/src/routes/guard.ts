import { useState } from "react";

import type { ClientState } from "../api/types";
import { useSpark } from "../store/useSpark";

/**
 * Route guards — which screens a URL alone may reach.
 *
 * WHY THESE EXIST
 *
 * The routes map onto the encounter's life, but until now nothing stopped a URL
 * from skipping to the middle of it. Typing `/call/consent` into the address bar
 * on a fresh store, and pressing Yes, reached the reveal with the scripted
 * identity — no encounter accepted, no call, no gate. The backend's gate
 * ordering was fixed first; this is the same defect on the client, where the
 * "gate" was only ever the order the screens happened to be visited in.
 *
 * A guard here is not a convenience. Invariant 2 says no identity before both
 * parties say yes AFTER THE CALL, and a path to the reveal that skips the call
 * breaks it whatever the adapter returns.
 *
 * THE STATE IS READ ONCE, AT MOUNT
 *
 * Every guarded screen announces its own state in an effect — `/call` sets
 * CONNECTED, `/call/consent` sets PENDING_CONSENT. If the guard re-read the
 * store it would be checking a value the screen had just written for itself,
 * which is not a check at all. So it captures the state the screen was ENTERED
 * with and holds it for the life of the mount.
 */

/** `/call` — you must have accepted an encounter to be in a call. */
const CALL_ENTRY: ReadonlySet<ClientState> = new Set([
  "PENDING_ACCEPT", // came through /encounter/waiting, the normal path
  "CONNECTED", // already in the call; a re-render must not evict you
]);

/**
 * `/call/consent` — the call must have ENDED, and ended through the screen that
 * can end it. Both exits from `/call` set CALL_ENDED, and nothing else does.
 */
const CONSENT_ENTRY: ReadonlySet<ClientState> = new Set([
  "CALL_ENDED",
  "PENDING_CONSENT", // this screen's own state, for a remount under StrictMode
]);

export const ENTRY_STATES = {
  call: CALL_ENTRY,
  consent: CONSENT_ENTRY,
} as const;

/**
 * The client state at the moment this screen was entered.
 *
 * Read from the store imperatively rather than through a selector: subscribing
 * would re-run the guard on every state change, including the one the screen
 * makes about itself.
 */
export function useEntryState(): ClientState {
  const [atMount] = useState<ClientState>(
    () => useSpark.getState().clientState,
  );
  return atMount;
}

/**
 * Where an invalid direct link should land.
 *
 * Not always `/home`: someone who is genuinely mid-call and reaches
 * `/call/consent` early belongs back in the call, and sending them home would
 * end an encounter that is still running. Everything else goes home, which is
 * the one screen that is true regardless of state.
 */
export function fallbackFor(state: ClientState): string {
  if (state === "CONNECTED" || state === "PENDING_ACCEPT") return "/call";
  return "/home";
}
