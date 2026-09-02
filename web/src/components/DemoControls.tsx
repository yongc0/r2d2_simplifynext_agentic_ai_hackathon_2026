import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import type { ConsentOutcome, DemoPersona } from "../api/types";
import { useSpark } from "../store/useSpark";

/**
 * The demo control strip — FRONTEND.md §8.
 *
 * "Six weeks of continuity has to fit inside five minutes." Hidden behind
 * `?demo=1`, and rendered OUTSIDE the phone so it is never mistaken for part of
 * the product.
 *
 * §8's requirement is that "every state must be reachable in under three
 * clicks", because "you will re-record more times than you expect". Each button
 * here is one click to a state that otherwise takes an evening, a week, or a
 * second participant to reach.
 *
 * EVERY ACTION IS AWAITED, and a failure is shown rather than swallowed. The
 * adapter's `reset` and `forceOutcome` used to return `void` while firing a
 * request and discarding the promise, so a take could begin before the reset
 * had reached the server — and the only symptom was the previous take's state
 * appearing in the recording, with nothing on screen to explain it. A demo
 * control that appears to work and does not is worse than one that is absent.
 */
export function DemoControls() {
  const navigate = useNavigate();
  const reset = useSpark((s) => s.reset);
  const seed = useSpark((s) => s.seed);
  const setWindowOpen = useSpark((s) => s.setWindowOpen);
  const setLockIns = useSpark((s) => s.setLockIns);
  const setBriefs = useSpark((s) => s.setBriefs);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Empty on MockAdapter, which has one scripted pair — the picker then hides
  // rather than offering a single option that changes nothing.
  const [personas, setPersonas] = useState<DemoPersona[]>([]);
  const [actingAs, setActingAs] = useState<string | null>(null);

  useEffect(() => {
    getAdapter()
      .getDemoPersonas()
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, []);

  /** Run one control, surfacing whatever it throws. */
  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : String(cause);
      setError(`${label}: ${detail}`);
    } finally {
      setBusy(false);
    }
  };

  const refreshContinuity = async () => {
    const adapter = getAdapter();
    const [lockIns, briefs] = await Promise.all([
      adapter.getLockIns(),
      adapter.getBriefs(),
    ]);
    setLockIns(lockIns);
    setBriefs(briefs);
  };

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-white/[0.08] bg-black/80 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-5xl flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
          <span className="mr-1 tracking-[0.18em] text-muted uppercase">
            demo
          </span>

          <Button
            busy={busy}
            onClick={() => navigate("/admin/profiles?demo=1")}
          >
            Profile lab
          </Button>

          <Button
            busy={busy}
            onClick={() =>
              run("skip to window", async () => {
                setWindowOpen(true);
                navigate("/encounter");
              })
            }
          >
            Skip to encounter window
          </Button>

          <Button
            busy={busy}
            onClick={() =>
              run("new encounter", async () => {
                // Keeps lock-ins and Date Studio memory, so a presenter can
                // show the recommender improving across encounters rather than
                // starting from nothing each time.
                await getAdapter().newEncounter();
                reset(seed);
                navigate("/encounter");
              })
            }
          >
            New encounter
          </Button>

          <Button
            busy={busy}
            onClick={() =>
              run("advance a day", async () => {
                await getAdapter().advanceDays(1);
                await refreshContinuity();
                navigate("/lockins");
              })
            }
          >
            +1 day
          </Button>

          <Button
            busy={busy}
            onClick={() =>
              run("advance a week", async () => {
                await getAdapter().advanceDays(7);
                await refreshContinuity();
                navigate("/lockins");
              })
            }
          >
            +1 week
          </Button>

          <span className="mx-1 h-4 w-px bg-white/10" />

          {/* Forces what the OTHER person does, so each branch can be filmed.
              It never changes what the viewer is shown for a given pair of
              answers — that is the thing invariant 3 is about. */}
          {(
            [
              ["both yes", "mutual"],
              ["they declined", "declined"],
              ["no answer", "no_response"],
            ] as [string, ConsentOutcome][]
          ).map(([label, outcome]) => (
            <Button
              key={outcome}
              busy={busy}
              onClick={() =>
                run(`force ${label}`, () => getAdapter().forceOutcome(outcome))
              }
            >
              {label}
            </Button>
          ))}

          <span className="mx-1 h-4 w-px bg-white/10" />

          <Button
            busy={busy}
            onClick={() =>
              run("reset", async () => {
                // The adapter first, then the store, then the route. Resetting
                // the store before the adapter had finished would leave a
                // half-reset take on screen if the adapter threw.
                await getAdapter().reset(seed);
                reset(seed);
                navigate("/home", { replace: true });
              })
            }
          >
            Reset (seed {seed})
          </Button>
        </div>

        {personas.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
            <span className="mr-1 tracking-[0.18em] text-muted uppercase">
              be
            </span>
            {personas.map((persona) => (
              <button
                key={persona.userId}
                type="button"
                disabled={busy}
                title={`${persona.intents.join(", ")} · ${persona.interests.join(", ")}`}
                onClick={() =>
                  run(`act as ${persona.handle}`, async () => {
                    await getAdapter().actAsPersona(persona.userId);
                    setActingAs(persona.userId);
                    reset(seed);
                    navigate("/home");
                  })
                }
                className={`rounded-full px-3 py-1.5 transition-colors disabled:opacity-40 ${
                  actingAs === persona.userId
                    ? "bg-accent/25 text-accent-soft"
                    : "bg-white/[0.07] text-text hover:bg-white/[0.14]"
                }`}
              >
                {persona.handle}
              </button>
            ))}
          </div>
        ) : null}

        {error ? (
          <p className="font-mono text-[11px] leading-relaxed text-rose-300">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function Button({
  children,
  onClick,
  busy,
}: {
  children: React.ReactNode;
  onClick: () => void;
  busy: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="rounded-full bg-white/[0.07] px-3 py-1.5 text-text transition-colors hover:bg-white/[0.14] disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/**
 * `?demo=1` — read once, from the URL the app was opened with.
 *
 * Deliberately not a keyboard shortcut like the Director panel: the strip is an
 * operator's tool, and a stray keypress revealing it mid-take is exactly the
 * kind of thing that costs a re-record.
 */
export function demoModeRequested(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("demo") === "1";
}
