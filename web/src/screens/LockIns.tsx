import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { PlanTheDateButton } from "../components/PlanTheDateButton";
import { PersonAvatar } from "../components/PersonAvatar";
import { MessageCircle } from "lucide-react";
import type { LockIn } from "../api/types";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { useSpark } from "../store/useSpark";

/**
 * /lockins — ten intentional connection slots.
 *
 * Ten slots rendered as ten slots, with empty ones visibly empty. Scarcity is
 * still legible at a glance without limiting a person to five connections.
 *
 * So the empty slots are drawn, not omitted. A list that grows from nothing
 * looks like an app with no data in it; ten outlines with one filled looks like
 * a product that has decided something. It is the same argument as the empty
 * home screen: the absence IS the feature, and it has to be visible to work.
 *
 * QUIET LOCK-INS ARE NOT NAGGED. §5.7 asks for "a distinct, non-guilting
 * treatment", and the wording matters more than the styling: no "it has been 12
 * days!", no streak, no red dot, no "don't lose this connection". A quiet
 * connection is a normal thing that happens between people, and a product that
 * bills it as a failure is teaching the wrong lesson to keep engagement up.
 *
 * INVARIANT 2 note: a `LockIn` carries an identity, and the adapter only
 * produces one after a mutual reveal — `MockAdapter.getLockIns()` is gated on
 * `revealed`, not on whether the notification was accepted. This screen renders
 * whatever it is given, so that gate is the one that matters.
 */
const SLOTS = 10;

export default function LockIns() {
  const lockIns = useSpark((s) => s.lockIns);
  const setLockIns = useSpark((s) => s.setLockIns);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const adapter = getAdapter();
        const nextLockIns = await adapter.getLockIns();
        if (cancelled) return;
        setLockIns(nextLockIns);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setLockIns]);

  const active = lockIns.filter((l) => l.state !== "released");
  const empty = Math.max(0, SLOTS - active.length);

  return (
    <div className={`flex h-full flex-col px-6 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-medium tracking-tight text-text">
          Lock-ins
        </h1>
        <p className="font-mono text-xs text-muted tabular-nums">
          {active.length} of {SLOTS}
        </p>
      </header>

      {error ? (
        <p className="mb-4 rounded-card bg-rose-100 px-4 py-3 text-xs font-medium leading-relaxed text-rose-800 ring-1 ring-rose-300 ring-inset">
          {error}
        </p>
      ) : null}

      <div className="no-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto">
        {lockIns.map((lockIn) => (
          <Slot
            key={lockIn.lockInId}
            lockIn={lockIn}
          />
        ))}
        {Array.from({ length: empty }, (_, i) => (
          <EmptySlot key={`empty-${i}`} />
        ))}
      </div>

      <p className="pt-5 text-center text-xs leading-relaxed text-muted">
        Ten at a time, so every connection still gets your attention.
      </p>
    </div>
  );
}

function Slot({
  lockIn,
}: {
  lockIn: LockIn;
}) {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const quiet = lockIn.state === "quiet";
  const released = lockIn.state === "released";

  return (
    <motion.article
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: released ? 0.35 : 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={`rounded-card p-4 ring-1 ring-inset ${
        quiet
          ? "bg-white/[0.02] ring-white/[0.05]"
          : "bg-surface ring-white/[0.06]"
      }`}
    >
      <div className="flex items-start gap-3">
        <PersonAvatar
          photo={lockIn.person.profilePhoto}
          seed={lockIn.person.avatarSeed}
          name={lockIn.person.displayName}
          size={44}
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-medium text-text">
              {lockIn.person.displayName}
            </h2>
            {/* Quiet is stated, once, as a fact. Not a warning, not a count of
                days, not a prompt to do something about it. */}
            {quiet ? (
              <span className="shrink-0 text-[11px] text-muted">quiet</span>
            ) : null}
            {!released ? (
              <button
                type="button"
                onClick={() => navigate(`/lockins/${lockIn.lockInId}/chat`)}
                aria-label={`Chat with ${lockIn.person.displayName}`}
                className="ml-auto grid size-9 shrink-0 place-items-center rounded-full bg-navy text-cream transition-transform hover:scale-105"
              >
                <MessageCircle size={16} aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <p className="text-xs text-muted">{connectedLabel(lockIn)}</p>

          {/* One tap to a real plan, on every live connection — not only the
              ones the Continuity Agent happened to write a brief for. The
              button already knows who this is, so it asks nothing: everything
              the planner needs is on the lock-in the server is holding. */}
          {!released ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <PlanTheDateButton lockInId={lockIn.lockInId} />
              <button
                type="button"
                onClick={() => navigate(`/plans/${lockIn.lockInId}`)}
                className="rounded-pill bg-cream px-4 py-2 text-xs font-semibold text-navy ring-1 ring-navy/15 ring-inset transition-colors hover:bg-peach/45"
              >
                Plan something
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </motion.article>
  );
}

function EmptySlot() {
  return (
    // Visibly empty, and shaped like the filled ones so the gap is obvious.
    // Dashed rather than solid so it reads as "space for someone" rather than
    // as a card that failed to load.
    <div
      className="grid h-[64px] place-items-center rounded-card border border-dashed border-navy/20 bg-cream/20"
      aria-label="Empty lock-in slot"
    >
      <span className="text-xs text-muted/50">Open slot</span>
    </div>
  );
}

/**
 * "connected 6 days ago", in words.
 *
 * Days, never a timestamp: the exact minute someone last spoke to you is the
 * kind of precision that turns into anxiety, and nothing here needs it.
 */
function connectedLabel(lockIn: LockIn): string {
  const opened = new Date(lockIn.openedAt).getTime();
  const last = lockIn.lastContactAt
    ? new Date(lockIn.lastContactAt).getTime()
    : opened;
  const days = Math.max(0, Math.round((last - opened) / 86_400_000));

  if (days === 0) return "connected today";
  if (days === 1) return "last spoke yesterday";
  return `last spoke ${days} days ago`;
}
