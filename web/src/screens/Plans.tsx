import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { PersonAvatar } from "../components/PersonAvatar";
import { DateMemoryPanel } from "../components/DateMemoryPanel";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import type { DateMemory, PlanLockIn } from "../api/types";
import { useSpark } from "../store/useSpark";
import { CalendarCheck, ChevronRight, HeartHandshake, Plus } from "lucide-react";

/**
 * `/plans` — the Date Studio hub.
 *
 * Spark finds one person a day. This is the half that runs afterwards, and the
 * reason to come back that is not "browse more people": choose a connection,
 * say what tonight should look like, and get three grounded options.
 *
 * WHAT IS DELIBERATELY NOT HERE
 *
 * No feed, no streaks, no "they are waiting for you", no compatibility scores,
 * no infinite list. The intended metric is weekly meaningful planning actions
 * per active lock-in, not time on screen — and every one of those patterns
 * optimises the second at the expense of the first.
 *
 * A connection that cannot be planned with is still listed, with the reason.
 * Hiding it would leave someone wondering where a person went, and the reasons
 * are ones they are entitled to know about.
 */
export default function Plans() {
  const navigate = useNavigate();
  const [lockIns, setLockIns] = useState<PlanLockIn[] | null>(null);
  const [memory, setMemory] = useState<DateMemory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const savedPlans = useSpark((state) => state.savedPlans);
  const savePlan = useSpark((state) => state.savePlan);
  const sharedIdeas = useSpark((state) => state.sharedDateIdeas);

  const load = async () => {
    try {
      const adapter = getAdapter();
      const [connections, remembered, itineraries] = await Promise.all([
        adapter.getPlanLockIns(),
        adapter.getDateMemory(),
        adapter.getItineraries(),
      ]);
      setLockIns(connections);
      setMemory(remembered);
      itineraries.forEach((itinerary) =>
        savePlan({ lockInId: itinerary.lockInId, itinerary }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setLockIns([]);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={`flex h-full flex-col px-6 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <h1 className="text-2xl font-medium tracking-tight text-text">Plans</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Every plan, organised by the person you are making it with.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => navigate("/plans/ideas")} className="inline-flex items-center justify-center gap-1.5 rounded-pill bg-navy px-3 py-2.5 text-xs font-semibold text-cream">
            <HeartHandshake size={14} /> Shared ideas {sharedIdeas.length ? `(${sharedIdeas.length})` : ""}
          </button>
          <button type="button" onClick={() => navigate("/plans/history")} className="inline-flex items-center justify-center gap-1.5 rounded-pill bg-cream px-3 py-2.5 text-xs font-semibold text-navy ring-1 ring-navy/15 ring-inset">
            <CalendarCheck size={14} /> Your dates
          </button>
        </div>
      </header>

      {error ? (
        <p className="mb-4 rounded-card bg-rose-100 px-4 py-3 text-xs font-medium leading-relaxed text-rose-800 ring-1 ring-rose-300 ring-inset">
          {error}
        </p>
      ) : null}

      <div className="no-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto">
        {lockIns === null ? (
          // Explicit loading state. A blank screen that might be empty and
          // might be broken is the worst of both.
          <p className="text-sm text-muted/70">Looking…</p>
        ) : lockIns.length === 0 ? (
          <div className="rounded-card bg-surface px-4 py-5 ring-1 ring-white/[0.06] ring-inset">
            <p className="text-sm leading-relaxed text-text/90">
              Planning opens once you and someone else have both said yes after
              a call.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              There is nothing to do here before that, and nothing to browse.
            </p>
          </div>
        ) : (
          lockIns.map((lockIn) => {
            const personPlans = savedPlans.filter((plan) => plan.lockInId === lockIn.lockInId);
            const personIdeas = sharedIdeas.filter((idea) => idea.lockInId === lockIn.lockInId);
            const blocked = Boolean(lockIn.unavailableReason);
            return (
              <section key={lockIn.lockInId} aria-labelledby={`plans-${lockIn.lockInId}`} className="overflow-hidden rounded-card bg-surface shadow-[0_10px_24px_-20px_rgba(2,0,13,0.55)] ring-1 ring-navy/10 ring-inset">
                <div className="flex items-center gap-3 border-b border-navy/10 p-4">
                  <PersonAvatar photo={lockIn.person.profilePhoto} seed={lockIn.person.avatarSeed} name={lockIn.person.displayName} size={46} />
                  <div className="min-w-0 flex-1">
                    <h2 id={`plans-${lockIn.lockInId}`} className="truncate text-base font-semibold text-text">{lockIn.person.displayName}</h2>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {lockIn.unavailableReason ?? `${personPlans.length} saved ${personPlans.length === 1 ? "plan" : "plans"} · ${personIdeas.length} shared ${personIdeas.length === 1 ? "idea" : "ideas"}`}
                    </p>
                  </div>
                  <button type="button" disabled={blocked} onClick={() => navigate(`/plans/${lockIn.lockInId}`)} aria-label={`Create a plan with ${lockIn.person.displayName}`} className="grid size-10 shrink-0 place-items-center rounded-full bg-navy text-cream disabled:opacity-35">
                    <Plus size={17} />
                  </button>
                </div>

                {personPlans.length > 0 ? (
                  <div className="px-4 py-3">
                    <p className="mb-2 text-[9px] font-semibold tracking-[0.16em] text-navy/60 uppercase">Saved plans</p>
                    {personPlans.map(({ itinerary }) => (
                      <button key={itinerary.itineraryId} type="button" onClick={() => navigate("/plans/history")} className="flex w-full items-center gap-3 border-t border-navy/10 py-2.5 text-left first:border-0 first:pt-0 last:pb-0">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-text">{itinerary.headline}</span>
                          <span className="mt-0.5 block truncate text-[11px] text-muted">{itinerary.dayLabel} · {itinerary.totalDurationMinutes} min · {itinerary.totalCostEstimate}</span>
                        </span>
                        <ChevronRight size={15} className="shrink-0 text-navy/55" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <button type="button" disabled={blocked} onClick={() => navigate(`/plans/${lockIn.lockInId}`)} className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-medium text-navy disabled:opacity-40">
                    Plan something with {lockIn.person.displayName}<ChevronRight size={15} />
                  </button>
                )}

                {personIdeas.length > 0 ? (
                  <button type="button" onClick={() => navigate("/plans/ideas")} className="flex w-full items-center justify-between border-t border-navy/10 bg-peach/25 px-4 py-3 text-xs font-semibold text-navy">
                    {personIdeas.length} shared {personIdeas.length === 1 ? "idea" : "ideas"}<ChevronRight size={15} />
                  </button>
                ) : null}
              </section>
            );
          })
        )}

        {lockIns && lockIns.length > 0 ? (
          <div className="mt-3">
            <DateMemoryPanel
              memory={memory}
              onCorrect={async (id, value) => {
                await getAdapter().correctDateMemory(id, value);
                await load();
              }}
              onForget={async (id) => {
                await getAdapter().forgetDateMemory(id);
                await load();
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
