import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { DateMemoryPanel } from "../components/DateMemoryPanel";
import { DatePlanCard } from "../components/DatePlanCard";
import type {
  Budget,
  DateMemory,
  DatePath,
  DatePreferences,
  Energy,
  Mood,
  PlanDuration,
  RejectionReason,
} from "../api/types";

/**
 * `/plans/:lockInId` — the planner for one connection.
 *
 * FIXED BOXES, NOT A CHAT BOX. Every constraint is a button, so the form works
 * without typing and without the system having to interpret a sentence.
 * Interpretation is where a recommender starts inventing, and these are also
 * the units the memory is stored in — so what Spark remembers can be shown back
 * word for word rather than paraphrased.
 *
 * REMEMBERING IS OPT-IN AND VISIBLE. "I am tired tonight" is context, not a
 * preference. The tickbox defaults to off, and when values arrive prefilled
 * from memory the screen says so — a preference someone did not notice being
 * applied is one they cannot correct.
 *
 * The safety boundary is the SERVER's. This screen redirects when there is no
 * eligible lock-in because that is better UX, but the adapter returns an empty
 * plan with a reason regardless of what the client does.
 */

const MOODS: [Mood, string][] = [
  ["easy", "Easy"],
  ["playful", "Playful"],
  ["adventurous", "Adventurous"],
  ["meaningful", "Meaningful"],
];
const BUDGETS: [Budget, string][] = [
  ["free", "Free"],
  ["under_20", "Under $20"],
  ["under_50", "Under $50"],
  ["flexible", "Any"],
];
const DURATIONS: [PlanDuration, string][] = [
  ["one_hour", "An hour"],
  ["two_hours", "A couple of hours"],
  ["whole_evening", "A whole evening"],
];
const ENERGIES: [Energy, string][] = [
  ["low", "Low"],
  ["medium", "Medium"],
  ["high", "High"],
];

export default function DateStudio() {
  const { lockInId = "" } = useParams();
  const navigate = useNavigate();

  const [prefs, setPrefs] = useState<DatePreferences | null>(null);
  const [remember, setRemember] = useState(false);
  const [paths, setPaths] = useState<DatePath[] | null>(null);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [memory, setMemory] = useState<DateMemory[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshMemory = async () => {
    setMemory(await getAdapter().getDateMemory(lockInId));
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getAdapter().getDatePreferences(lockInId);
        if (!cancelled) setPrefs(loaded);
        await refreshMemory();
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lockInId]);

  const set = <K extends keyof DatePreferences>(
    key: K,
    value: DatePreferences[K],
  ) => {
    setPrefs((current) =>
      current ? { ...current, [key]: current[key] === value ? null : value } : current,
    );
  };

  const generate = async () => {
    if (!prefs) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await getAdapter().generateDatePlans(lockInId, {
        mood: prefs.mood,
        budget: prefs.budget,
        duration: prefs.duration,
        energy: prefs.energy,
        formats: prefs.formats,
        timeBucket: prefs.timeBucket,
        remember,
      });
      setPaths(plan.paths);
      setNote(plan.note);
      await refreshMemory();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const feedback = async (
    planId: string,
    action: "saved" | "rejected",
    reasons: RejectionReason[] = [],
  ) => {
    await getAdapter().sendDateFeedback(planId, action, reasons);
    if (action === "saved") {
      setSaved((current) => new Set(current).add(planId));
    } else {
      // Regenerate, so the effect of the rejection is visible immediately
      // rather than the next time somebody happens to come back.
      await generate();
    }
    await refreshMemory();
  };

  if (!prefs && error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
        <p className="text-sm leading-relaxed text-muted">{error}</p>
        <button
          type="button"
          onClick={() => navigate("/plans", { replace: true })}
          className="rounded-pill bg-white/[0.06] px-5 py-2.5 text-sm text-text"
        >
          Back to plans
        </button>
      </div>
    );
  }

  return (
    <div className={`flex h-full flex-col px-6 pt-16 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-4">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="mb-2 text-xs text-muted underline-offset-2 hover:text-text hover:underline"
        >
          ← Plans
        </button>
        <h1 className="text-xl font-medium tracking-tight text-text">
          What should tonight look like?
        </h1>
        {prefs?.prefilled ? (
          // Said out loud. Values quietly applied from memory are values
          // nobody knows to correct.
          <p className="mt-1.5 text-xs text-accent-soft">
            We have filled in what you usually pick. Change anything.
          </p>
        ) : null}
      </header>

      <div className="no-scrollbar flex flex-1 flex-col gap-5 overflow-y-auto">
        {prefs ? (
          <>
            <Boxes
              label="Mood"
              options={MOODS}
              selected={prefs.mood ?? null}
              onSelect={(v) => set("mood", v)}
            />
            <Boxes
              label="Budget"
              options={BUDGETS}
              selected={prefs.budget ?? null}
              onSelect={(v) => set("budget", v)}
            />
            <Boxes
              label="How long"
              options={DURATIONS}
              selected={prefs.duration ?? null}
              onSelect={(v) => set("duration", v)}
            />
            <Boxes
              label="Energy"
              options={ENERGIES}
              selected={prefs.energy ?? null}
              onSelect={(v) => set("energy", v)}
            />
            {prefs.sharedBuckets.length > 0 ? (
              <Boxes
                label="When you are both free"
                options={prefs.sharedBuckets.map(
                  (b) => [b, b.replace(/_/g, " ")] as [string, string],
                )}
                selected={prefs.timeBucket ?? null}
                onSelect={(v) => set("timeBucket", v)}
              />
            ) : null}

            <label className="flex items-center gap-2.5 text-xs text-muted">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="size-4 accent-[color:var(--color-accent)]"
              />
              Remember this preference for next time
            </label>

            <button
              type="button"
              onClick={generate}
              disabled={busy}
              className="w-full rounded-pill bg-accent px-6 py-3.5 text-sm font-medium text-text transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Thinking…" : "Generate plans"}
            </button>
          </>
        ) : null}

        {error && prefs ? (
          <p className="rounded-card bg-rose-500/10 px-4 py-3 text-xs text-rose-200 ring-1 ring-rose-400/20 ring-inset">
            {error}
          </p>
        ) : null}

        {paths !== null ? (
          <section className="flex flex-col gap-3">
            {paths.map((path, i) => (
              <DatePlanCard
                key={path.pathId}
                path={path}
                index={i}
                saved={saved.has(path.pathId)}
                onSave={() => feedback(path.pathId, "saved")}
                onReject={(reasons) => feedback(path.pathId, "rejected", reasons)}
              />
            ))}
            {paths.length === 0 || note ? (
              // Never pad the list; say why it is short.
              <p className="rounded-card bg-surface px-4 py-3 text-xs leading-relaxed text-muted ring-1 ring-white/[0.06] ring-inset">
                {note || "Nothing fits those constraints. Try relaxing one."}
              </p>
            ) : null}
          </section>
        ) : null}

        <DateMemoryPanel
          memory={memory}
          onCorrect={async (id, value) => {
            await getAdapter().correctDateMemory(id, value);
            await refreshMemory();
          }}
          onForget={async (id) => {
            await getAdapter().forgetDateMemory(id);
            await refreshMemory();
          }}
        />
      </div>
    </div>
  );
}

/**
 * One row of selectable boxes.
 *
 * Buttons with `aria-pressed`, so the state is announced rather than only
 * coloured, and the whole form is reachable by keyboard without typing.
 * Selecting the chosen option again clears it — "no opinion" has to be
 * reachable, or the first tap becomes permanent.
 */
function Boxes<T extends string>({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: [T, string][];
  selected: T | null;
  onSelect: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-[10px] tracking-[0.18em] text-muted uppercase">
        {label}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map(([value, text]) => {
          const active = selected === value;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(value)}
              className={`rounded-pill px-3.5 py-2 text-[13px] ring-1 ring-inset transition-colors ${
                active
                  ? "bg-accent/25 text-accent-soft ring-accent/30"
                  : "bg-white/[0.04] text-text/85 ring-white/[0.08] hover:bg-white/[0.08]"
              }`}
            >
              {text}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
