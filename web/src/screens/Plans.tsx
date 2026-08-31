import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { Avatar } from "../components/Avatar";
import { DateMemoryPanel } from "../components/DateMemoryPanel";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import type { DateMemory, PlanLockIn } from "../api/types";

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

  const load = async () => {
    try {
      const adapter = getAdapter();
      const [connections, remembered] = await Promise.all([
        adapter.getPlanLockIns(),
        adapter.getDateMemory(),
      ]);
      setLockIns(connections);
      setMemory(remembered);
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
    <div className={`flex h-full flex-col px-6 pt-16 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <h1 className="text-2xl font-medium tracking-tight text-text">Plans</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Something to do with the people you have already met.
        </p>
      </header>

      {error ? (
        <p className="mb-4 rounded-card bg-rose-500/10 px-4 py-3 text-xs leading-relaxed text-rose-200 ring-1 ring-rose-400/20 ring-inset">
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
          lockIns.map((lockIn) => (
            <ConnectionRow
              key={lockIn.lockInId}
              lockIn={lockIn}
              onOpen={() => navigate(`/plans/${lockIn.lockInId}`)}
            />
          ))
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

function ConnectionRow({
  lockIn,
  onOpen,
}: {
  lockIn: PlanLockIn;
  onOpen: () => void;
}) {
  const blocked = Boolean(lockIn.unavailableReason);

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={blocked}
      className="flex items-center gap-3 rounded-card bg-surface px-3.5 py-3 text-left ring-1 ring-white/[0.06] ring-inset transition-colors hover:bg-white/[0.07] disabled:opacity-50 disabled:hover:bg-surface"
    >
      <Avatar seed={lockIn.person.avatarSeed} size={40} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-text">
          {lockIn.person.displayName}
        </span>
        <span className="block truncate text-xs text-muted">
          {/* The reason, not a dead button. */}
          {lockIn.unavailableReason ?? "Plan something"}
        </span>
      </span>
    </button>
  );
}
