import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";

import { getAdapter } from "../api/adapter";
import type { EncounterCard } from "../api/types";
import { useSpark } from "../store/useSpark";

/**
 * /encounter — the notification (FRONTEND.md §5.3).
 *
 * The single most important visual in the video, and the screen where the whole
 * product argument is either made or lost. What is on it:
 *
 *   a headline, a line of context, when your paths crossed in WORDS, and two
 *   buttons.
 *
 * What is not on it, and must never be: a name, a photo, an age, an initial, a
 * distance, a place, a map, a blurred silhouette. The silhouette matters — it
 * is the one people reach for, and it implies an appearance, which is the exact
 * judgement this product exists to remove.
 *
 * The card this renders (`EncounterCard`) has no field for any of them, so the
 * omission is structural rather than a matter of restraint.
 */
export default function Encounter() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const setCard = useSpark((s) => s.setCard);
  const setClientState = useSpark((s) => s.setClientState);

  const [card, setLocalCard] = useState<EncounterCard | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = await getAdapter().getEncounter();
      if (cancelled || !next) return;
      setLocalCard(next);
      setCard(next);
      setClientState("NOTIFIED");
    })();
    return () => {
      cancelled = true;
    };
  }, [setCard, setClientState]);

  const respond = async (accept: boolean) => {
    if (!card) return;
    await getAdapter().respondToEncounter(card.encounterId, accept);

    // THE TWO ANSWERS LEAVE DIFFERENT STATES BEHIND.
    //
    // Both used to set PENDING_ACCEPT, and the `/call` guard admits that state
    // — so declining an encounter left the client still eligible to enter the
    // call it had just refused. The guard was doing its job; it was being told
    // the wrong thing.
    //
    // ABANDONED rather than CLOSED, to match what the backend records for a
    // decline at the notification: the encounter never became a call.
    setClientState(accept ? "PENDING_ACCEPT" : "ABANDONED");

    // A decline goes to the same close-out as everything else. From the other
    // side this is indistinguishable from a no-show, which is the point.
    navigate(accept ? "/encounter/waiting" : "/encounter/closed", {
      replace: true,
    });
  };

  if (!card) {
    // Reserved space rather than a spinner: the layout must not jump when the
    // card arrives, and this screen is on camera.
    return <div className="h-full" aria-busy="true" />;
  }

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="flex h-full flex-col justify-between px-9 pt-24 pb-12"
    >
      <div className="flex flex-col gap-5">
        <h1 className="text-[2rem] leading-[1.15] font-medium tracking-tight text-text">
          You crossed paths today.
        </h1>
        <p className="text-base leading-relaxed text-muted">
          Someone here might be worth three minutes.
        </p>

        {/* The overlap, in words. Produced by `overlapHintFor` from a coarse
            time bucket — there is no code path from here to a place. */}
        <p className="text-sm text-accent-soft italic">{card.overlapHint}</p>
      </div>

      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => respond(true)}
          className="w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-text transition-opacity hover:opacity-90"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => respond(false)}
          className="w-full rounded-pill px-6 py-4 text-base text-muted transition-colors hover:text-text"
        >
          Not tonight
        </button>
        <p className="pt-2 text-center text-xs text-muted/70">
          Three minutes, voice only. No names unless you both say yes.
        </p>
      </div>
    </motion.div>
  );
}
