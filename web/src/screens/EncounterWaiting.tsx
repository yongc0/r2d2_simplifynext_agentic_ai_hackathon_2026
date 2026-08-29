import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";

import { CLOSE_OUT_DELAY_MS } from "../components/CloseOut";
import { useSpark } from "../store/useSpark";

/**
 * /encounter/waiting — accepted, waiting for the other side (§5.3).
 *
 * A soft pulse and one line. Deliberately says nothing about the other party:
 * not whether they have been notified, not whether they have opened it, not
 * whether they are typing, deciding, or asleep. Every one of those is a signal,
 * and INVARIANT 2 forbids all of them.
 *
 * It times out into the same close-out every other non-connection reaches, so
 * "they declined" and "they never looked" arrive at an identical screen.
 */
export default function EncounterWaiting() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const setClientState = useSpark((s) => s.setClientState);

  useEffect(() => {
    setClientState("PENDING_ACCEPT");
    // In the scripted demo the other side accepts. `?demo=1` controls (§8) and
    // the mock's forced outcomes drive the other branches.
    const timer = setTimeout(() => navigate("/call", { replace: true }), 2400);
    return () => clearTimeout(timer);
  }, [navigate, setClientState]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 px-9 text-center">
      <motion.span
        aria-hidden="true"
        className="block size-3 rounded-full bg-accent"
        animate={reduced ? undefined : { opacity: [0.35, 1, 0.35], scale: [1, 1.35, 1] }}
        transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
      />
      <p className="text-sm leading-relaxed text-muted">
        Waiting for the other person.
      </p>
    </div>
  );
}

/** How long this screen waits before giving up. Shared with every other
 *  close-out path so the timing cannot differ between them. */
export const WAITING_TIMEOUT_MS = CLOSE_OUT_DELAY_MS;
