import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { ItineraryView } from "../components/ItineraryView";
import { ReflectionForm } from "../components/ReflectionForm";
import type { Itinerary, ItineraryStatus, Reflection } from "../api/types";

/**
 * `/plans/history` — the dates you have planned, and how they went.
 *
 * EVERY STATUS IS LISTED, CANCELLED ONES INCLUDED. A history that quietly hid
 * the evenings that did not happen would be a highlight reel, and the person
 * was there — they already know. It would also make the one honest use of this
 * screen impossible: looking back at what worked.
 *
 * WHAT IS NOT ON THIS SCREEN
 *
 * Anything about the other person's side of it. There is no "they confirmed",
 * no "waiting on them", no indication of whether they wrote a reflection, and
 * no status meaning they turned you down. A plan they did not take up reads as
 * `cancelled`, exactly like one nobody got round to — invariant 2's rule, still
 * holding long after the reveal.
 */

const STATUS_LABEL: Record<ItineraryStatus, string> = {
  draft: "Draft",
  proposed: "Proposed",
  confirmed: "Confirmed",
  completed: "Completed",
  cancelled: "Cancelled",
};

const STATUS_STYLE: Record<ItineraryStatus, string> = {
  draft: "bg-white/[0.08] text-muted",
  proposed: "bg-sky-400/15 text-sky-200",
  confirmed: "bg-emerald-400/15 text-emerald-200",
  completed: "bg-accent/20 text-accent-soft",
  cancelled: "bg-white/[0.06] text-muted/70",
};

export default function DateHistory() {
  const navigate = useNavigate();
  const [itineraries, setItineraries] = useState<Itinerary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [reflecting, setReflecting] = useState<string | null>(null);
  const [reflection, setReflection] = useState<Reflection | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getAdapter().getItineraries();
        if (!cancelled) setItineraries(rows);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
          setItineraries([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const replace = (next: Itinerary) =>
    setItineraries((rows) =>
      (rows ?? []).map((row) =>
        row.itineraryId === next.itineraryId ? next : row,
      ),
    );

  const setStatus = async (
    itinerary: Itinerary,
    status: "proposed" | "confirmed" | "cancelled",
  ) => {
    try {
      replace(await getAdapter().setItineraryStatus(itinerary.itineraryId, status));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const openReflection = async (itinerary: Itinerary) => {
    setReflecting(itinerary.itineraryId);
    setReflection(null);
    try {
      setReflection(await getAdapter().getReflection(itinerary.itineraryId));
    } catch {
      // Not having written one is the normal state, not an error worth a
      // banner. The form opens blank.
    }
  };

  return (
    <div className={`flex h-full flex-col px-6 pt-16 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="mb-3 text-xs text-muted transition-colors hover:text-text"
        >
          ← Plans
        </button>
        <h1 className="text-2xl font-medium tracking-tight text-text">
          Your dates
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Everything you have planned, in whatever state it ended up.
        </p>
      </header>

      {error ? (
        <p role="alert" className="mb-4 text-xs leading-relaxed text-rose-300">
          {error}
        </p>
      ) : null}

      {itineraries === null ? (
        <p className="text-sm text-muted">Loading your dates…</p>
      ) : itineraries.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-6">
          <p className="text-sm text-text">Nothing planned yet.</p>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            When you and someone you have met plan an evening, it will be here —
            with the times, the places, and somewhere to say how it went
            afterwards.
          </p>
          <button
            type="button"
            onClick={() => navigate("/plans")}
            className="mt-4 rounded-full bg-accent/20 px-4 py-2 text-xs font-medium text-accent-soft"
          >
            Plan something
          </button>
        </div>
      ) : (
        <ul className="space-y-3 overflow-y-auto">
          {itineraries.map((itinerary) => {
            const open = openId === itinerary.itineraryId;
            return (
              <li
                key={itinerary.itineraryId}
                className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3"
              >
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() =>
                    setOpenId(open ? null : itinerary.itineraryId)
                  }
                  className="flex w-full items-start justify-between gap-3 text-left"
                >
                  <span className="min-w-0">
                    <span className="block text-sm break-words text-text">
                      {itinerary.headline}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted">
                      {itinerary.dayLabel} · {itinerary.stops.length} stop
                      {itinerary.stops.length === 1 ? "" : "s"} ·{" "}
                      {itinerary.totalCostEstimate}
                    </span>
                  </span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${STATUS_STYLE[itinerary.status]}`}
                  >
                    {STATUS_LABEL[itinerary.status]}
                  </span>
                </button>

                {open ? (
                  <div className="mt-4 space-y-4 border-t border-white/[0.06] pt-4">
                    <ItineraryView
                      itinerary={itinerary}
                      onChange={replace}
                      readOnly={
                        itinerary.status === "completed" ||
                        itinerary.status === "cancelled"
                      }
                    />

                    <div className="flex flex-wrap gap-2">
                      {itinerary.status === "draft" ? (
                        <Action
                          label="Mark as proposed"
                          onClick={() => setStatus(itinerary, "proposed")}
                        />
                      ) : null}
                      {itinerary.status === "proposed" ? (
                        <Action
                          label="We're on"
                          onClick={() => setStatus(itinerary, "confirmed")}
                        />
                      ) : null}
                      {itinerary.status !== "completed" &&
                      itinerary.status !== "cancelled" ? (
                        <Action
                          label="Call it off"
                          onClick={() => setStatus(itinerary, "cancelled")}
                        />
                      ) : null}
                      {itinerary.status === "confirmed" ||
                      itinerary.status === "completed" ? (
                        <Action
                          label={
                            itinerary.hasReflection
                              ? "Edit how it went"
                              : "How did it go?"
                          }
                          onClick={() => openReflection(itinerary)}
                        />
                      ) : null}
                    </div>

                    {reflecting === itinerary.itineraryId ? (
                      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] px-4 py-4">
                        <ReflectionForm
                          itineraryId={itinerary.itineraryId}
                          existing={reflection}
                          onSaved={() => {
                            replace({
                              ...itinerary,
                              status: "completed",
                              hasReflection: true,
                            });
                            setReflecting(null);
                          }}
                        />
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Action({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full bg-white/[0.07] px-3 py-1.5 text-[11px] text-text transition-colors hover:bg-white/[0.14]"
    >
      {label}
    </button>
  );
}
