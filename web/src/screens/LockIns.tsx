import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { PlanTheDateButton } from "../components/PlanTheDateButton";
import { Avatar } from "../components/Avatar";
import type { ContinuityBrief, LockIn } from "../api/types";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { useSpark } from "../store/useSpark";

/**
 * /lockins — the five slots (FRONTEND.md §5.7).
 *
 * "Five slots rendered as five slots, with empty ones visibly empty. Scarcity is
 * the point and should be legible at a glance."
 *
 * So the empty slots are drawn, not omitted. A list that grows from nothing
 * looks like an app with no data in it; five outlines with one filled looks like
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
const SLOTS = 5;

export default function LockIns() {
  const lockIns = useSpark((s) => s.lockIns);
  const briefs = useSpark((s) => s.briefs);
  const setLockIns = useSpark((s) => s.setLockIns);
  const setBriefs = useSpark((s) => s.setBriefs);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const adapter = getAdapter();
        const [nextLockIns, nextBriefs] = await Promise.all([
          adapter.getLockIns(),
          adapter.getBriefs(),
        ]);
        if (cancelled) return;
        setLockIns(nextLockIns);
        setBriefs(nextBriefs);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setLockIns, setBriefs]);

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
        <p className="mb-4 rounded-card bg-rose-500/10 px-4 py-3 text-xs leading-relaxed text-rose-200 ring-1 ring-rose-400/20 ring-inset">
          {error}
        </p>
      ) : null}

      <div className="no-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto">
        {lockIns.map((lockIn) => (
          <Slot
            key={lockIn.lockInId}
            lockIn={lockIn}
            brief={briefs.find((b) => b.lockInId === lockIn.lockInId)}
          />
        ))}
        {Array.from({ length: empty }, (_, i) => (
          <EmptySlot key={`empty-${i}`} />
        ))}
      </div>

      <p className="pt-5 text-center text-xs leading-relaxed text-muted">
        Five at a time, so each one gets your attention.
      </p>
    </div>
  );
}

function Slot({
  lockIn,
  brief,
}: {
  lockIn: LockIn;
  brief: ContinuityBrief | undefined;
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
        <Avatar seed={lockIn.person.avatarSeed} size={44} />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h2 className="truncate text-base font-medium text-text">
              {lockIn.person.displayName}
            </h2>
            {/* Quiet is stated, once, as a fact. Not a warning, not a count of
                days, not a prompt to do something about it. */}
            {quiet ? (
              <span className="shrink-0 text-[11px] text-muted">quiet</span>
            ) : null}
          </div>
          <p className="text-xs text-muted">{connectedLabel(lockIn)}</p>

          {/* One tap to a real plan, on every live connection — not only the
              ones the Continuity Agent happened to write a brief for. The
              button already knows who this is, so it asks nothing: everything
              the planner needs is on the lock-in the server is holding. */}
          {!released ? (
            <div className="mt-3">
              <PlanTheDateButton lockInId={lockIn.lockInId} />
            </div>
          ) : null}

          {brief ? (
            <div className="mt-3 border-l-2 border-accent/40 pl-3">
              {/* The Continuity Agent cites something the pair actually
                  discussed. A brief with nothing to cite is a reminder, not
                  continuity, and the backend does not produce one. */}
              <p className="text-sm leading-relaxed text-text/90 italic">
                {brief.line}
              </p>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-pill bg-white/[0.06] px-4 py-2 text-xs text-text transition-colors hover:bg-white/[0.1]"
                >
                  {brief.suggestedAction}
                </button>
                {/* The other half of the product: not only staying in touch,
                    but doing something. Post-reveal only — a lock-in exists
                    because two people already exchanged names. */}
                <button
                  type="button"
                  onClick={() => navigate(`/plans/${lockIn.lockInId}`)}
                  className="rounded-pill bg-accent/20 px-4 py-2 text-xs text-accent-soft ring-1 ring-accent/25 ring-inset transition-colors hover:bg-accent/30"
                >
                  Plan something
                </button>
              </div>
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
      className="grid h-[76px] place-items-center rounded-card border border-dashed border-white/[0.07]"
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
