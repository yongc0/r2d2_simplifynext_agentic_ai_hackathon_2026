import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { HeartHandshake, Mic2, Sparkles } from "lucide-react";

import { getAdapter } from "../api/adapter";
import { Avatar } from "../components/Avatar";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { useSpark } from "../store/useSpark";

/**
 * /home — spontaneous encounter state. There is intentionally no countdown:
 * when an encounter is ready, the call can begin immediately.
 */

export default function Home() {
  const navigate = useNavigate();
  const lockIns = useSpark((s) => s.lockIns);
  const setLockIns = useSpark((s) => s.setLockIns);
  const forcedOpen = useSpark((s) => s.windowOpen);
  // An empty profile is the one thing that genuinely blocks the product from
  // working, so it is the one thing home will interrupt itself to mention.
  const chips = useSpark((s) => s.chips);

  const open = forcedOpen;

  // The lock-in list, if there is one. Failure is silent here on purpose: this
  // screen's job is to be calm, and an error banner about a list that is empty
  // anyway would be the loudest thing on it. `/lockins` reports properly.
  useEffect(() => {
    let cancelled = false;
    getAdapter()
      .getLockIns()
      .then((next) => {
        if (!cancelled) setLockIns(next);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [setLockIns]);

  const active = lockIns.filter((l) => l.state !== "released");

  return (
    <div className={`flex h-full flex-col px-6 ${NAV_HEIGHT_CLASS}`}>
      <div className="flex flex-col gap-3">
        <p className="text-[10px] font-semibold tracking-[0.2em] text-navy/60 uppercase">
          On Spark
        </p>
        <h1 className="max-w-[19rem] text-[1.75rem] leading-[1.12] font-semibold tracking-tight text-text">
          {open ? "Someone just crossed your path." : "Your next encounter will arrive spontaneously."}
        </h1>

        {open ? (
          <p className="text-sm leading-relaxed text-muted">
            Your anonymous three-minute call is ready now.
          </p>
        ) : (
          <p className="text-sm leading-relaxed text-muted">
            There is no timer to watch. We will let you know the moment a suitable encounter is available.
          </p>
        )}
      </div>

      {open ? (
        <button
          type="button"
          onClick={() => navigate("/encounter")}
          className="mt-8 w-full rounded-pill bg-navy px-6 py-4 text-base font-semibold text-cream shadow-[0_10px_24px_-14px_rgba(7,32,63,0.8)] transition-transform hover:-translate-y-0.5"
        >
          Start the encounter
        </button>
      ) : null}

      {/* Set-up, but only while it is missing. Home is calm because there is
          nothing to scroll — not because it refuses to tell you the product
          cannot match you yet. */}
      {chips.length === 0 ? (
        <button
          type="button"
          onClick={() => navigate("/profile")}
          className="mt-8 w-full rounded-card bg-surface px-4 py-4 text-left shadow-[0_10px_24px_-20px_rgba(2,0,13,0.6)] ring-1 ring-navy/10 ring-inset transition-transform hover:-translate-y-0.5"
        >
          <span className="block text-sm text-text">Set up your profile</span>
          <span className="mt-1 block text-xs leading-relaxed text-muted">
            Spark needs to know what you are here for before it can find anyone.
          </span>
        </button>
      ) : null}

      <section
        aria-labelledby="tonight-works"
        className="mt-8 rounded-card bg-navy p-5 text-cream shadow-[0_14px_32px_-20px_rgba(7,32,63,0.9)]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[9px] font-semibold tracking-[0.18em] text-cream/75 uppercase">
              One encounter, your pace
            </p>
            <h2 id="tonight-works" className="mt-1 text-lg font-semibold">
              How encounters work
            </h2>
          </div>
          <span className="rounded-pill bg-cream/10 px-2.5 py-1 text-[9px] font-semibold tracking-wide text-cream ring-1 ring-cream/25 ring-inset">
            PRIVATE
          </span>
        </div>

        <ol className="mt-4 grid gap-3">
          <HomeStep
            Icon={Sparkles}
            title="Any moment"
            detail="A suitable encounter can begin spontaneously."
          />
          <HomeStep
            Icon={Mic2}
            title="Three minutes"
            detail="An anonymous voice call with a hard stop."
          />
          <HomeStep
            Icon={HeartHandshake}
            title="You both choose"
            detail="Names unlock only after two private yeses."
          />
        </ol>
      </section>

      {/* Below the fold: the lock-ins, and nothing else. No feed, no
          suggestions, no "people you might like". */}
      {active.length > 0 ? (
        <section className="mt-12 flex flex-col gap-2">
          <h2 className="mb-1 text-[10px] tracking-[0.2em] text-muted uppercase">
            Lock-ins
          </h2>
          {active.map((lockIn) => (
            <button
              key={lockIn.lockInId}
              type="button"
              onClick={() => navigate("/lockins")}
              className="flex items-center gap-3 rounded-card bg-surface px-3.5 py-3 text-left shadow-[0_8px_20px_-18px_rgba(2,0,13,0.7)] ring-1 ring-navy/10 ring-inset transition-transform hover:-translate-y-0.5"
            >
              <Avatar seed={lockIn.person.avatarSeed} size={36} />
              <span className="truncate text-sm text-text">
                {lockIn.person.displayName}
              </span>
              {lockIn.state === "quiet" ? (
                <span className="ml-auto shrink-0 text-[11px] text-muted">
                  quiet
                </span>
              ) : null}
            </button>
          ))}
        </section>
      ) : null}

      {active.length > 0 ? (
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="mt-4 w-full rounded-pill bg-cream/70 px-6 py-3 text-sm font-medium text-navy ring-1 ring-navy/10 ring-inset transition-colors hover:bg-cream"
        >
          Plan something
        </button>
      ) : null}

      <div className="flex-1" />

      <p className="text-center text-xs font-medium leading-relaxed text-muted">
        One person a day. Three minutes. No names unless you both say yes.
      </p>
    </div>
  );
}
function HomeStep({
  Icon,
  title,
  detail,
}: {
  Icon: typeof Sparkles;
  title: string;
  detail: string;
}) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-peach text-navy">
        <Icon size={16} strokeWidth={2} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-[12px] font-semibold text-cream">{title}</span>
        <span className="block text-[11px] leading-relaxed text-cream/80">{detail}</span>
      </span>
    </li>
  );
}
