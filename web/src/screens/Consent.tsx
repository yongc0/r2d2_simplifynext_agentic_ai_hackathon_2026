import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";

import { getAdapter } from "../api/adapter";
import { CLOSE_OUT_DELAY_MS, CloseOut } from "../components/CloseOut";
import type { ConsentOutcome, RevealedPerson } from "../api/types";
import { ENTRY_STATES, fallbackFor, useEntryState } from "../routes/guard";
import { useSpark } from "../store/useSpark";

/**
 * /call/consent — the decision (FRONTEND.md §5.5).
 *
 * Three phases: the question, a genuinely uncertain wait, and then either the
 * reveal or a close-out.
 *
 * INVARIANT 3 lives here, and it is enforced three ways:
 *
 *   THE WAIT IS MEASURED FROM THE CLICK, NOT FROM THE RESPONSE. This code used
 *   to start `CLOSE_OUT_DELAY_MS` *after* awaiting `submitConsent`, so the real
 *   wait was network time plus the delay — and the mutual branch does strictly
 *   more work than the others, both here and on the server. A viewer with a
 *   stopwatch could have read the outcome off the clock before the screen said
 *   anything. The comment claimed otherwise, which is how it survived review.
 *
 *   Now a deadline is stamped before the request goes out, and the outcome is
 *   shown on a MULTIPLE of that delay — so a response slower than the window
 *   rounds up to the next one instead of leaking the extra milliseconds. See
 *   `revealAt`.
 *
 *   THE OUTCOME IS COLLAPSED IMMEDIATELY. `submitConsent` distinguishes
 *   `declined` from `no_response` so the demo controls can film both, and the
 *   very next thing this screen does is throw that distinction away. Below the
 *   `mutual` check there is no value in scope that knows which it was.
 *
 *   THE CLOSE SCREEN TAKES NO PROPS. `<CloseOut />` cannot vary with an
 *   argument it is never given.
 *
 * And the waiting state is honest: no hopeful animation, no "fingers crossed",
 * nothing that would make the close-out land as a let-down. §5.5 — "Do not
 * animate a hopeful outcome before it is known."
 */
type Phase = "asking" | "waiting" | "closed";

export default function Consent() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const setClientState = useSpark((s) => s.setClientState);
  const setRevealed = useSpark((s) => s.setRevealed);
  const setConsentOutcome = useSpark((s) => s.setConsentOutcome);

  // GUARD. The gate opens because a call ended, not because a URL was typed.
  // Without this, `/call/consent` on a fresh store plus one click on Yes
  // reached the reveal with the scripted identity — no encounter, no call.
  const entry = useEntryState();
  const allowed = ENTRY_STATES.consent.has(entry);

  const [phase, setPhase] = useState<Phase>("asking");
  const [failed, setFailed] = useState<string | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (allowed) setClientState("PENDING_CONSENT");
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, [allowed, setClientState]);

  const answer = async (yes: boolean) => {
    setPhase("waiting");
    setFailed(null);

    // STAMPED BEFORE THE REQUEST. Everything below measures from here, so the
    // clock starts when the person answers rather than when the server does.
    const askedAt = performance.now();

    const card = useSpark.getState().card;
    let result: { outcome: ConsentOutcome; person: RevealedPerson | null };
    try {
      result = await getAdapter().submitConsent(card?.encounterId ?? "", yes);
    } catch (cause) {
      setFailed(cause instanceof Error ? cause.message : String(cause));
      return;
    }

    // The store keeps the fine-grained outcome for the Director panel and the
    // demo controls. Nothing that RENDERS may read it — see the invariant note
    // above, and the test that renders all three endings and diffs them.
    setConsentOutcome(result.outcome);

    const isMutual = result.outcome === "mutual";
    const timer = setTimeout(() => {
      if (isMutual && result.person) {
        setRevealed(result.person);
        setClientState("REVEALED");
        navigate("/reveal", { replace: true });
      } else {
        // Everything that is not a mutual yes ends here, identically.
        setClientState("CLOSED");
        setPhase("closed");
      }
    }, revealAt(askedAt));
    timers.current.push(timer);
  };

  if (!allowed) return <Navigate to={fallbackFor(entry)} replace />;

  if (failed) {
    // A transport failure is not one of the three outcomes, so it gets its own
    // screen and says nothing about what the answer was. Retrying re-asks the
    // question rather than resubmitting silently: the person should choose
    // again, not have an unsent answer replayed on their behalf.
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-9 text-center">
        <h1 className="text-xl font-medium text-text">
          That did not go through.
        </h1>
        <p className="text-sm leading-relaxed text-muted">{failed}</p>
        <button
          type="button"
          onClick={() => {
            setFailed(null);
            setPhase("asking");
          }}
          className="mt-2 rounded-pill bg-white/[0.06] px-6 py-3 text-sm text-text transition-colors hover:bg-white/[0.1]"
        >
          Ask me again
        </button>
      </div>
    );
  }

  if (phase === "closed") return <CloseOut />;

  if (phase === "waiting") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 px-9 text-center">
        <motion.span
          aria-hidden="true"
          className="block size-3 rounded-full bg-muted"
          animate={
            reduced ? undefined : { opacity: [0.3, 0.9, 0.3] }
          }
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        />
        {/* Neutral by design. Not "fingers crossed", not "hoping for a match" —
            the outcome is genuinely unknown and the copy says exactly that. */}
        <p className="text-sm leading-relaxed text-muted">
          Thanks. We will let you know if you both said yes.
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="flex h-full flex-col justify-between px-9 pt-28 pb-12"
    >
      <div className="flex flex-col gap-4">
        <h1 className="text-[2rem] leading-[1.15] font-medium tracking-tight text-text">
          Would you like to connect?
        </h1>
        {/* States the rule plainly, so a "no" feels like a private choice
            rather than a rejection sent to someone. */}
        <p className="text-sm leading-relaxed text-muted">
          We will only tell either of you if you both say yes.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => answer(true)}
          className="w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-cream transition-opacity hover:opacity-90"
        >
          Yes
        </button>
        <button
          type="button"
          onClick={() => answer(false)}
          className="w-full rounded-pill px-6 py-4 text-base text-muted transition-colors hover:text-text"
        >
          No
        </button>
      </div>
    </motion.div>
  );
}

/**
 * How long to keep waiting, measured from the moment the person answered.
 *
 * Not `CLOSE_OUT_DELAY_MS` minus elapsed, which would go to zero as soon as a
 * response took longer than the window and hand the remaining timing straight
 * back to the network. Instead the outcome appears on a MULTIPLE of the delay:
 * at 2.6s, or 5.2s, or 7.8s. A response that takes 300ms and one that takes
 * 2,400ms are shown at the same moment, and only a difference large enough to
 * cross a whole window is observable at all.
 *
 * This is timing quantisation, and it is the same reasoning as the fixed delay
 * it replaces: the screen must not be a channel that says what the copy
 * refuses to.
 *
 * Exported so the policy can be asserted directly. Timing a real render is
 * flaky; the arithmetic is not.
 */
export function revealAt(askedAt: number): number {
  const elapsed = performance.now() - askedAt;
  const windows = Math.max(1, Math.ceil(elapsed / CLOSE_OUT_DELAY_MS));
  return windows * CLOSE_OUT_DELAY_MS - elapsed;
}
