import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

/**
 * Guardian — the discreet exit (FRONTEND.md §5.8, ARCHITECTURE §13.7).
 *
 * WHAT IS AND IS NOT BUILT HERE
 *
 * Built: the trigger, the in-app interruption, the exit, and a check-in whose
 * two answers do different things — "something felt off" closes the encounter
 * without ever opening the reveal gate, so a name cannot be exchanged with
 * someone who has just been flagged.
 *
 * NOT built: anything server-side. `GuardianAgent` and `IncidentLog` exist in
 * `spark/src/agents/guardian.py` with their own tests, but no API route
 * connects them, so a concern raised here is not recorded anywhere durable and
 * no human is notified. That gap is stated in docs/PILOT.md rather than implied
 * away — a check-in that silently goes nowhere is exactly the thing this
 * component must not become.
 *
 * A small unlabelled affordance during a call. Triggering it produces a plain
 * in-app interruption that gives the person a reason to step away, followed by
 * a private check-in.
 *
 * THE LINE THIS COMPONENT DOES NOT CROSS
 *
 * CLAUDE.md: "Do not make Guardian Mode imitate a system or OS-level alert. It
 * is a safety feature, not a deception tool."
 *
 * So this is styled unmistakably as Spark: the product's own surface, its own
 * accent, its own wordmark. There is no fake status bar, no battery warning, no
 * iOS call sheet, no green-and-red circles, no "Unknown number". The excuse it
 * shows is a REMINDER THE PERSON SET, and it says so — the interruption is
 * theirs, not an impersonation of their operating system.
 *
 * Two reasons that matters. The obvious one is that imitating system chrome to
 * manipulate the observer is a deception pattern we would be teaching. The less
 * obvious one is that it does not work: anyone who has seen the real thing
 * recognises a fake, and a person relying on this to leave a bad situation
 * deserves something that does not fall apart when examined.
 *
 * The excuse is PRECONFIGURED, mirroring `_DEFAULT_EXCUSES` on the Python side:
 * the person chooses their own words while they are calm, not while they are
 * trying to get out of a room.
 */

/** Mirrors `_DEFAULT_EXCUSES` in `spark/src/agents/guardian.py`. */
const EXCUSE = "Your reminder: you said you needed to leave by now.";

type Stage = "idle" | "interrupting" | "checking-in" | "done";

export function useGuardian() {
  const [stage, setStage] = useState<Stage>("idle");
  return {
    stage,
    trigger: () => setStage("interrupting"),
    dismiss: () => setStage("idle"),
    stepAway: () => setStage("checking-in"),
    finish: () => setStage("done"),
  };
}

/**
 * The unlabelled trigger.
 *
 * Recognisable to the person who set it up, unremarkable to anyone watching
 * over their shoulder — so it has no icon, no colour, and an accessible name
 * that a screen reader will read but a shoulder will not.
 */
export function GuardianTrigger({ onTrigger }: { onTrigger: () => void }) {
  return (
    <button
      type="button"
      aria-label="Guardian"
      onClick={onTrigger}
      className="grid size-11 place-items-center rounded-full text-muted/40 transition-colors hover:text-muted"
    >
      <span className="block size-1.5 rounded-full bg-current" />
    </button>
  );
}

export function GuardianOverlay({
  stage,
  onDismiss,
  onStepAway,
  onFine,
  onConcern,
}: {
  stage: Stage;
  onDismiss: () => void;
  onStepAway: () => void;
  /** They are all right. The encounter continues to the gate as normal. */
  onFine: () => void;
  /** Something felt off. This must have a consequence — see `Call.tsx`. */
  onConcern: () => void;
}) {
  const reduced = useReducedMotion();

  return (
    <AnimatePresence>
      {stage === "interrupting" || stage === "checking-in" ? (
        <motion.div
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="absolute inset-0 z-40 flex items-end bg-bg/80 p-5 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={
            stage === "interrupting" ? "Your reminder" : "Private check-in"
          }
        >
          <motion.div
            initial={reduced ? false : { y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { y: 40, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="w-full rounded-card bg-surface p-5 ring-1 ring-white/[0.08] ring-inset"
          >
            {stage === "interrupting" ? (
              <>
                {/* Says whose reminder this is, in the product's own voice.
                    Never "Incoming call", never a carrier, never a number. */}
                <p className="mb-2 text-[10px] tracking-[0.2em] text-accent-soft uppercase">
                  Spark · your reminder
                </p>
                <p className="mb-5 text-base leading-relaxed text-text">
                  {EXCUSE}
                </p>
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={onStepAway}
                    className="w-full rounded-pill bg-accent px-6 py-3.5 text-sm font-medium text-cream transition-opacity hover:opacity-90"
                  >
                    Step away now
                  </button>
                  <button
                    type="button"
                    onClick={onDismiss}
                    className="w-full rounded-pill px-6 py-3 text-sm text-muted transition-colors hover:text-text"
                  >
                    Not now
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="mb-2 text-[10px] tracking-[0.2em] text-accent-soft uppercase">
                  Private
                </p>
                <p className="mb-1.5 text-base leading-relaxed text-text">
                  Are you all right?
                </p>
                {/* Stated plainly, because the person needs to know before they
                    answer. Nothing here reaches the other party — the consent
                    ledger is append-only and never joined into anything they
                    can see (INVARIANT 5). */}
                <p className="mb-5 text-xs leading-relaxed text-muted">
                  This stays between you and us. The other person is not told
                  that you used this, or that the call ended early.
                </p>
                {/* Two answers, two outcomes. They were wired to the same
                    handler, which made the check-in a question with no
                    consequence — the worst kind to ask someone who has just
                    used a safety feature. */}
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={onFine}
                    className="w-full rounded-pill bg-white/[0.06] px-6 py-3.5 text-sm text-text transition-colors hover:bg-white/[0.1]"
                  >
                    I am fine
                  </button>
                  <button
                    type="button"
                    onClick={onConcern}
                    className="w-full rounded-pill bg-white/[0.06] px-6 py-3.5 text-sm text-text transition-colors hover:bg-white/[0.1]"
                  >
                    Something felt off
                  </button>
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-muted/70">
                  If something felt off, we will not ask whether you want to
                  swap names.
                </p>
              </>
            )}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
