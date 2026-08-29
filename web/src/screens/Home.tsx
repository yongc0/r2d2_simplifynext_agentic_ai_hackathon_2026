import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { Avatar } from "../components/Avatar";
import { useSpark } from "../store/useSpark";

/**
 * /home — the waiting state (FRONTEND.md §5.2).
 *
 * "Deliberately, almost aggressively empty. One line of copy and a countdown to
 * the evening encounter window. Below: the lock-in list if any exist. Nothing
 * else. No feed, no browse, no profiles, no activity. The emptiness is the
 * product argument — there is nothing here to scroll."
 *
 * That is the hardest instruction in the spec to follow, because every instinct
 * says to put something here. There is nothing here on purpose: a product whose
 * claim is "one person a day, three minutes" cannot also be somewhere you spend
 * an evening, and a home screen with a feed on it would say the opposite of
 * everything the rest of the app says.
 *
 * The countdown is the only moving thing, and it is honest — it counts to the
 * next 9pm, not to a number chosen to look good on camera.
 */

/**
 * The evening window, in local time. One hour, once a day.
 *
 * It CLOSES. The first version counted down to 21:00 and then reported the
 * window open for the rest of time, because `msUntilWindow` returned 0 for
 * everything past 9pm — which quietly turned a one-hour window into a permanent
 * one. The scarcity is the product; a window that never shuts is a feed with a
 * countdown in front of it.
 */
const WINDOW_OPENS_HOUR = 21;
const WINDOW_CLOSES_HOUR = 22;

type WindowPhase = "before" | "open" | "closed";

interface WindowStatus {
  phase: WindowPhase;
  /** Until it opens, until it closes, or until it opens again tomorrow. */
  msRemaining: number;
}

/** Where the evening currently is. Exported for the test. */
export function windowStatus(now: Date = new Date()): WindowStatus {
  const opens = new Date(now);
  opens.setHours(WINDOW_OPENS_HOUR, 0, 0, 0);
  const closes = new Date(now);
  closes.setHours(WINDOW_CLOSES_HOUR, 0, 0, 0);

  if (now < opens) {
    return { phase: "before", msRemaining: opens.getTime() - now.getTime() };
  }
  if (now < closes) {
    return { phase: "open", msRemaining: closes.getTime() - now.getTime() };
  }
  // Tonight is over. The next one is tomorrow, and saying so is the honest
  // version of "nothing here" — not an open window with nothing behind it.
  const tomorrow = new Date(opens);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return { phase: "closed", msRemaining: tomorrow.getTime() - now.getTime() };
}

export default function Home() {
  const navigate = useNavigate();
  const lockIns = useSpark((s) => s.lockIns);
  const setLockIns = useSpark((s) => s.setLockIns);
  const forcedOpen = useSpark((s) => s.windowOpen);

  const [status, setStatus] = useState<WindowStatus>(() => windowStatus());

  useEffect(() => {
    // Derived from the clock each tick rather than latched into the store. The
    // store's `windowOpen` is the OPERATOR's override (§8) and is never written
    // from here — otherwise forcing it open and then letting the clock run
    // would leave the two fighting over the same flag.
    const id = setInterval(() => setStatus(windowStatus()), 1000);
    return () => clearInterval(id);
  }, []);

  // Forced open by the demo strip, or genuinely open. Five minutes of recording
  // does not contain an evening, so the override exists — but it is additive,
  // and it cannot make the phase say something the clock disagrees with.
  const open = forcedOpen || status.phase === "open";

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
    <div className="flex h-full flex-col px-8 pt-24 pb-10">
      <div className="flex flex-col gap-3">
        <h1 className="text-[1.6rem] leading-snug font-medium tracking-tight text-text">
          {open
            ? "Your encounter window is open."
            : status.phase === "closed"
              ? "Tonight's window has closed."
              : "Your encounter window opens at 9:00pm."}
        </h1>

        {open ? (
          <p className="text-sm leading-relaxed text-muted">
            One person crossed your path today.
            {!forcedOpen ? ` Closes in ${formatCountdown(status.msRemaining)}.` : ""}
          </p>
        ) : (
          <>
            <p className="font-mono text-[2.5rem] leading-none tracking-tight text-accent-soft tabular-nums">
              {formatCountdown(status.msRemaining)}
            </p>
            {status.phase === "closed" ? (
              <p className="text-sm leading-relaxed text-muted">
                Until it opens again tomorrow.
              </p>
            ) : null}
          </>
        )}
      </div>

      {open ? (
        <button
          type="button"
          onClick={() => navigate("/encounter")}
          className="mt-8 w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-text transition-opacity hover:opacity-90"
        >
          Open tonight's encounter
        </button>
      ) : null}

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
              className="flex items-center gap-3 rounded-card bg-surface px-3.5 py-3 text-left ring-1 ring-white/[0.06] ring-inset transition-colors hover:bg-white/[0.07]"
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

      <div className="flex-1" />

      <p className="text-center text-xs leading-relaxed text-muted/70">
        One person a day. Three minutes. No names unless you both say yes.
      </p>
    </div>
  );
}

function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
