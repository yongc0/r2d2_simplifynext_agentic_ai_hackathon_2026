import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import type { DatePath, RejectionReason } from "../api/types";

/**
 * One of the three offers.
 *
 * Shows the itinerary, the bands, and WHY — the evidence the ranking actually
 * used, not a sentence written first and justified afterwards.
 *
 * The three actions are Save, Not for us, and Refine. Note what is absent: no
 * rating, no stars, no "how did it go". Spark does not ask whether a date went
 * well or whether somebody liked you. That is not ours to grade, and a product
 * that scores it teaches people to perform.
 */

/** The shape labels. Categories describing the PLAN, never the people. */
const SHAPE_LABEL: Record<string, string> = {
  easy: "Easy",
  new: "Something new",
  light: "Keep it light",
};

const BAND_LABEL: Record<string, string> = {
  free: "Free",
  under_20: "Under $20",
  under_50: "Under $50",
  flexible: "Any budget",
  one_hour: "About an hour",
  two_hours: "A couple of hours",
  whole_evening: "A whole evening",
};

/** Why it was not right. Chips, never a text box — a reason has to be something
 *  the ranking can act on, and "meh" is not. */
const REASONS: [RejectionReason, string][] = [
  ["too_expensive", "Too expensive"],
  ["too_long", "Too long"],
  ["too_active", "Too active"],
  ["too_quiet", "Too quiet"],
  ["too_crowded", "Too crowded"],
  ["wrong_time", "Wrong time"],
  ["already_done", "Already done it"],
  ["not_our_style", "Not our style"],
];

export function DatePlanCard({
  path,
  index,
  saved,
  onSave,
  onReject,
}: {
  path: DatePath;
  index: number;
  saved: boolean;
  onSave: () => void;
  onReject: (reasons: RejectionReason[]) => void;
}) {
  const reduced = useReducedMotion();
  const [rejecting, setRejecting] = useState(false);

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
      aria-label={`${SHAPE_LABEL[path.shape] ?? path.shape} plan`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded-pill bg-accent/20 px-2.5 py-1 text-[10px] tracking-[0.14em] text-accent-soft uppercase">
          {SHAPE_LABEL[path.shape] ?? path.shape}
        </span>
        <span className="text-[11px] text-muted">
          {BAND_LABEL[path.budgetBand] ?? path.budgetBand} ·{" "}
          {BAND_LABEL[path.durationBand] ?? path.durationBand} ·{" "}
          {path.proposedBucket.replace("_", " ")}
        </span>
      </div>

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
                // Beside the venue, in the same breath. §13.6 — a partner is
                // disclosed where it is read, never in a footnote.
                <span className="ml-1.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900 ring-1 ring-amber-300 ring-inset">
                  Spark partner
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>

      {/* The evidence. Every clause here moved the score. */}
      <p className="mb-3 border-l-2 border-accent/40 pl-3 text-xs leading-relaxed text-muted italic">
        {path.rationale}
      </p>

      {path.groundedIn.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {path.groundedIn.map((interest) => (
            <span
              key={interest}
              className="rounded-pill bg-white/[0.05] px-2.5 py-1 text-[11px] text-text/80"
            >
              {interest}
            </span>
          ))}
        </div>
      ) : null}

      {rejecting ? (
        <div>
          <p className="mb-2 text-xs text-muted">What was wrong with it?</p>
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map(([reason, label]) => (
              <button
                key={reason}
                type="button"
                onClick={() => {
                  onReject([reason]);
                  setRejecting(false);
                }}
                className="rounded-pill bg-white/[0.06] px-3 py-1.5 text-[11px] text-text transition-colors hover:bg-white/[0.12]"
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setRejecting(false)}
            className="mt-2 text-[11px] text-muted underline-offset-2 hover:underline"
          >
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onSave}
            disabled={saved}
            aria-pressed={saved}
            className="rounded-pill bg-emerald-600 px-4 py-2 text-xs font-semibold text-white ring-1 ring-emerald-700 ring-inset transition-colors hover:bg-emerald-700 disabled:opacity-60"
          >
            {saved ? "Saved" : "Save"}
          </button>
          <button
            type="button"
            onClick={() => setRejecting(true)}
            className="rounded-pill bg-white/[0.06] px-4 py-2 text-xs text-text transition-colors hover:bg-white/[0.1]"
          >
            Not for us
          </button>
        </div>
      )}
    </motion.article>
  );
}
