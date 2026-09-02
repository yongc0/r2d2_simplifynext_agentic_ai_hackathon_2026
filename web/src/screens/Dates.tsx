import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";

import { getAdapter } from "../api/adapter";
import type { DatePath, DatePlan } from "../api/types";
import { useSpark } from "../store/useSpark";

/**
 * /dates — three evenings for a pair who have already exchanged names.
 *
 * This is the half of the product that is not waiting. Spark finds one person a
 * day; this is what it does once you have found them. "We should meet sometime"
 * is where most of these connections quietly die, and a single venue is only
 * slightly easier to accept than nothing — so the agent offers three shapes of
 * evening and the pair pick one.
 *
 * THIS IS THE ONLY SCREEN ALLOWED TO POINT SOMEWHERE, AND HERE IS WHY
 *
 * Invariant 1 forbids rendering a place. A date plan obviously names places, so
 * the two are reconciled by WHEN and by WHAT:
 *
 *   WHEN — it is gated on a mutual reveal, on both sides. This component
 *   redirects without one, and the backend returns 409. Two people who have
 *   exchanged names and are choosing where to meet are picking a destination
 *   together; that is not a disclosure of where either of them was.
 *
 *   WHAT — a stop is a KIND of place ("a hawker centre, one dish each and
 *   swap"), never a named business at an address. `DateStop` has no field for
 *   an address, a distance or a map, and the backend never gives the venue
 *   search a location — so "near where you both were" cannot be assembled from
 *   anything on this screen.
 *
 * Commercial partners are labelled beside the venue, never in fine print
 * (§13.6). `isCommercialPartner` is required on `DateStop`, so a partner cannot
 * be rendered without its label.
 */
export default function Dates() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const person = useSpark((s) => s.revealed);
  const card = useSpark((s) => s.card);

  const [plan, setPlan] = useState<DatePlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!person) return;
    let cancelled = false;
    (async () => {
      try {
        const next = await getAdapter().getDatePlan(card?.encounterId ?? "");
        if (!cancelled) setPlan(next);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [person, card]);

  // The guard, mirroring the backend's. No mutual reveal, no plan — and
  // nowhere on this screen that could name a place to someone who has not
  // reached that point.
  if (!person) return <Navigate to="/home" replace />;

  return (
    <div className="flex h-full flex-col px-6 pt-16 pb-10">
      <header className="mb-1">
        <h1 className="text-2xl font-medium tracking-tight text-text">
          Something to do
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Three ideas for you and {person.displayName}, from what you both said.
        </p>
      </header>

      <div className="no-scrollbar mt-6 flex flex-1 flex-col gap-3 overflow-y-auto">
        {error ? (
          <p className="rounded-card bg-rose-100 px-4 py-3 text-xs font-medium leading-relaxed text-rose-800 ring-1 ring-rose-300 ring-inset">
            {error}
          </p>
        ) : null}

        {plan?.paths.map((path, i) => (
          <PathCard key={path.pathId} path={path} index={i} reduced={!!reduced} />
        ))}

        {plan && plan.paths.length === 0 ? (
          // Honest emptiness. The note says why, so a blank screen reads as a
          // fact about these two rather than as something broken.
          <p className="rounded-card bg-surface px-4 py-4 text-sm leading-relaxed text-muted ring-1 ring-white/[0.06] ring-inset">
            {plan.note || "Nothing to suggest just yet."}
          </p>
        ) : null}

        {plan && plan.paths.length > 0 && plan.note ? (
          <p className="px-1 pt-1 text-xs leading-relaxed text-muted/70">
            {plan.note}
          </p>
        ) : null}
      </div>

      <button
        type="button"
        onClick={() => navigate("/lockins", { replace: true })}
        className="mt-5 w-full rounded-pill bg-white/[0.06] px-6 py-3.5 text-sm text-text transition-colors hover:bg-white/[0.1]"
      >
        Back to lock-ins
      </button>
    </div>
  );
}

function PathCard({
  path,
  index,
  reduced,
}: {
  path: DatePath;
  index: number;
  reduced: boolean;
}) {
  return (
    <motion.article
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.3,
        delay: reduced ? 0 : index * 0.06,
        ease: [0.22, 1, 0.36, 1],
      }}
      className="rounded-card bg-surface p-4 ring-1 ring-white/[0.06] ring-inset"
    >
      <p className="mb-3 text-[15px] leading-snug font-medium text-text">
        {path.headline}
      </p>

      <ol className="mb-3 flex flex-col gap-1.5">
        {path.stops.map((stop, i) => (
          <li key={stop.venueId} className="flex gap-2.5 text-[13px]">
            <span className="shrink-0 text-muted/50 tabular-nums">{i + 1}</span>
            <span className="text-text/85">
              {stop.activity}
              {stop.isCommercialPartner ? (
                // Beside the venue, in the same sentence. §13.6 — a partner
                // venue is disclosed where it is read, not in a footnote.
                <span className="ml-1.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300 ring-inset">
                  Spark partner
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>

      {/* Why THESE two. Grounded in interests both of them listed — the agent
          will not build a path it cannot cite. */}
      <p className="border-l-2 border-accent/40 pl-3 text-xs leading-relaxed text-muted italic">
        {path.rationale}
      </p>
    </motion.article>
  );
}
