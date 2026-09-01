import { useState } from "react";

import { getAdapter } from "../api/adapter";
import type { Itinerary, ItineraryStop } from "../api/types";
import { RouteMap } from "./RouteMap";

/**
 * One evening, in order, with times — the thing the whole planner exists to
 * produce.
 *
 * Not a list of suggestions. Every stop says where, when, how long, roughly
 * what it costs, how you get there from the last one, and why it was chosen;
 * and the stops are joined into a single schedule that adds up. "We should meet
 * sometime" is where most of these connections die, and this is what replaces
 * it.
 *
 * THE THREE OPENING STATES ARE RENDERED AS THREE THINGS
 *
 * `unknown` is not styled as a softer `open`. OpenStreetMap's hours coverage is
 * patchy, and a plan that quietly presents "we don't know" as "it's open" is
 * how two people end up outside a locked door. `closed` never reaches here at
 * all — the schema refuses to construct a stop that is shut when you arrive.
 */
export function ItineraryView({
  itinerary,
  onChange,
  readOnly = false,
}: {
  itinerary: Itinerary;
  onChange?: (next: Itinerary) => void;
  readOnly?: boolean;
}) {
  const [activeStopId, setActiveStopId] = useState<string | null>(null);
  const [busyOrder, setBusyOrder] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const replace = async (order: number) => {
    setBusyOrder(order);
    setNotice(null);
    try {
      const result = await getAdapter().replaceItineraryStop(
        itinerary.itineraryId,
        order,
      );
      // The server hands back the UNCHANGED plan alongside a reason when it
      // cannot find an alternative. Showing the reason and keeping the plan is
      // the whole contract: a failed swap must not cost somebody the evening
      // they already had.
      if (result.itinerary) onChange?.(result.itinerary);
      if (result.reason) setNotice(result.reason);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusyOrder(null);
    }
  };

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <h2 className="text-base leading-snug font-medium text-text">
          {itinerary.headline}
        </h2>
        <p className="text-xs text-muted">
          {itinerary.dayLabel} · about {formatDuration(itinerary.totalDurationMinutes)}{" "}
          · {itinerary.totalCostEstimate}
        </p>
      </header>

      <RouteMap
        stops={itinerary.stops}
        attribution={itinerary.attribution}
        activeStopId={activeStopId}
        onSelectStop={(id) => setActiveStopId(id === activeStopId ? null : id)}
      />

      <ol className="space-y-2">
        {itinerary.stops.map((stop) => (
          <li key={stop.stopId}>
            {stop.travelFromPrevious ? (
              <p className="flex items-center gap-1.5 py-1.5 pl-4 text-[11px] text-muted">
                <span aria-hidden>↓</span>
                <span>
                  {stop.travelFromPrevious.minutes} min{" "}
                  {stop.travelFromPrevious.mode}
                  {/* Said out loud, every time. An estimate that looks measured
                      is the kind of small dishonesty that makes somebody miss a
                      booking. */}
                  <span className="text-muted/70"> (estimated)</span>
                </span>
              </p>
            ) : null}

            <StopCard
              stop={stop}
              active={activeStopId === stop.stopId}
              onSelect={() =>
                setActiveStopId(activeStopId === stop.stopId ? null : stop.stopId)
              }
              onReplace={readOnly ? undefined : () => replace(stop.order)}
              busy={busyOrder === stop.order}
            />
          </li>
        ))}
      </ol>

      {itinerary.note ? (
        <p className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-100/80">
          {itinerary.note}
        </p>
      ) : null}

      {notice ? (
        <p
          role="status"
          className="rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-[11px] leading-relaxed text-muted"
        >
          {notice}
        </p>
      ) : null}
    </section>
  );
}

function StopCard({
  stop,
  active,
  onSelect,
  onReplace,
  busy,
}: {
  stop: ItineraryStop;
  active: boolean;
  onSelect: () => void;
  onReplace?: () => void;
  busy: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border px-3 py-3 transition-colors ${
        active
          ? "border-accent/40 bg-accent/[0.07]"
          : "border-white/[0.08] bg-white/[0.03]"
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-expanded={active}
        className="flex w-full items-start gap-3 text-left"
      >
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/20 text-[11px] font-semibold text-accent-soft">
          {stop.order}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-medium break-words text-text">
              {stop.venueName}
            </span>
            {stop.isCommercialPartner ? (
              // Beside the venue, never in fine print.
              <span className="rounded-full bg-white/[0.08] px-1.5 py-0.5 text-[10px] text-muted">
                a Spark partner venue
              </span>
            ) : null}
          </span>
          <span className="mt-0.5 block text-[11px] text-muted">
            {stop.startTime}–{stop.endTime} · {stop.estimatedCost}
          </span>
        </span>
      </button>

      {active ? (
        <div className="mt-3 space-y-2 border-t border-white/[0.06] pt-3">
          <p className="text-[11px] leading-relaxed text-muted">{stop.rationale}</p>

          <p className="text-[11px] leading-relaxed text-muted">
            {stop.address ?? (
              // Never a guess assembled from surrounding streets.
              <span className="text-muted/70">Address not listed</span>
            )}
          </p>

          <OpeningState stop={stop} />

          <div className="flex flex-wrap gap-2 pt-1">
            <a
              href={stop.mapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full bg-accent/20 px-3 py-1.5 text-[11px] font-medium text-accent-soft transition-colors hover:bg-accent/30"
            >
              Navigate
            </a>
            {onReplace ? (
              <button
                type="button"
                onClick={onReplace}
                disabled={busy}
                className="rounded-full bg-white/[0.07] px-3 py-1.5 text-[11px] text-text transition-colors hover:bg-white/[0.14] disabled:opacity-40"
              >
                {busy ? "Finding another…" : "Swap this stop"}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Open, or explicitly unknown.
 *
 * Two visually distinct states, because they are two different facts. A stop
 * that is `closed` cannot reach this component — `ItineraryStop` refuses to
 * validate one — so there is no third branch to render.
 */
function OpeningState({ stop }: { stop: ItineraryStop }) {
  if (stop.openingState === "open") {
    return (
      <p className="text-[11px] text-emerald-300/80">
        Open then{stop.openingHours ? ` · ${stop.openingHours}` : ""}
      </p>
    );
  }
  return (
    <p className="text-[11px] text-amber-200/80">
      Opening hours are not recorded for this venue — worth checking before you
      go.
    </p>
  );
}

function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  if (rest === 0) return `${hours} hr`;
  return `${hours} hr ${rest} min`;
}
