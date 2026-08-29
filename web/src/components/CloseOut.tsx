/**
 * The end of an encounter that did not become a connection.
 *
 * INVARIANT 3 IS ENFORCED BY THIS COMPONENT'S SIGNATURE.
 *
 * Look at what it is not given: the outcome, the other party's answer, the
 * user's own answer, or anything that could carry one. It takes nothing at all.
 * It therefore cannot vary with any of them, however this file is later edited.
 *
 * This is the same move as `build_close_out(encounter_id, viewer_id,
 * call_ended)` on the Python side, and for the same reason: a screen that says
 * something warmer when the user was the one who declined is a channel, and
 * every such channel eventually tells someone they were rejected.
 *
 * The copy is fixed. There is no count of declines, no "they were not ready",
 * no "you have been passed on N times", and no branch that could produce one.
 */
export function CloseOut() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-9 text-center">
      <h1 className="text-2xl leading-snug font-medium text-text">
        That one is closed.
      </h1>
      <p className="text-sm leading-relaxed text-muted">
        Your next encounter is tomorrow at 9pm.
      </p>
    </div>
  );
}

/**
 * How long the app waits between an answer and the close-out.
 *
 * A single constant, used by every path that can reach this screen. If the
 * delay were "however long the other person took to answer", the clock would
 * say what the words refuse to: a fast close means an early decline, a slow one
 * means they thought about it. So the wait is fixed, and it is fixed in one
 * place so no branch can quietly differ.
 */
export const CLOSE_OUT_DELAY_MS = 2600;
