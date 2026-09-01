import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import type { Itinerary } from "../api/types";

/**
 * "Plan the Date ✨" — one tap, from a connection to a real evening.
 *
 * IT ASKS NOTHING, AND THAT IS THE POINT. The button already knows which
 * connection this is; the server already knows what the two of them have in
 * common, when they are both free, what this person has told Spark to remember,
 * and what they thought of previous plans. Making somebody re-enter any of that
 * before they can see a suggestion is how a one-tap feature becomes a form.
 *
 * The full Date Studio is still there for anybody who wants to steer — this is
 * the fast path, not the only path.
 *
 * WHAT IT WILL NOT DO
 *
 * Show something when there is nothing honest to show. If Spark has no venue
 * data, or nothing that fits is open when the two of them are free, this says
 * so in the server's own words instead of producing an evening nobody can
 * actually have.
 */
export function PlanTheDateButton({
  lockInId,
  onPlanned,
  className,
}: {
  lockInId: string;
  onPlanned?: (itinerary: Itinerary) => void;
  className?: string;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const plan = async () => {
    setBusy(true);
    setProblem(null);
    try {
      // No preferences: everything the planner needs is already stored against
      // this lock-in. `remember` is deliberately absent — a one-tap plan is not
      // somebody stating a durable preference.
      const result = await getAdapter().createItinerary(lockInId, {});
      if (!result.itinerary) {
        setProblem(result.reason);
        return;
      }
      if (onPlanned) {
        onPlanned(result.itinerary);
      } else {
        navigate("/plans/history");
      }
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={className}>
      <button
        type="button"
        onClick={plan}
        disabled={busy}
        className="rounded-pill bg-accent/20 px-4 py-2 text-xs text-accent-soft ring-1 ring-accent/25 ring-inset transition-colors hover:bg-accent/30 disabled:opacity-50"
      >
        {busy ? "Planning…" : "Plan the Date ✨"}
      </button>

      {problem ? (
        <p
          role="status"
          className="mt-2 text-[11px] leading-relaxed text-muted"
        >
          {problem}
        </p>
      ) : null}
    </div>
  );
}
