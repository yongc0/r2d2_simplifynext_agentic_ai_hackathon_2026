import { useState } from "react";

import { getAdapter } from "../api/adapter";
import type { Reflection, ReflectionAspect, ReflectionDraft } from "../api/types";

/**
 * How the date went — for the person who was on it, and for nobody else.
 *
 * THE PRIVACY IS THE FEATURE, NOT A SETTING
 *
 * "Would you be open to a second date?" is only answerable honestly if the
 * answer cannot travel. So it does not: there is no adapter method that returns
 * somebody else's reflection, no field on an itinerary saying whether the other
 * person filled one in, and nothing this form submits is observable by them —
 * no notification, no status change on their side, and no silence that begins
 * the moment it is sent. Nobody is ever told they were turned down.
 *
 * The promise is stated on the form itself, every time. A privacy guarantee the
 * person is not shown is not one they can rely on.
 *
 * WHAT SPARK DOES WITH IT
 *
 * Almost nothing, on purpose. The whole reflection is kept for its author. Only
 * a rating of the PLACE or the ACTIVITY can influence what gets suggested next,
 * and even then only as an ordinary "this shape did not land" — the same signal
 * a thumbs-down on a plan produces. Conversation, chemistry and comfort are the
 * most important things here and are read by nothing: a quiet conversation is
 * not evidence a venue was wrong, and a recommender that treats "we did not
 * click" as "book somewhere louder" is inventing a preference from a feeling.
 */

const ASPECTS: { key: ReflectionAspect; label: string; hint: string }[] = [
  { key: "conversation", label: "Conversation", hint: "How it flowed" },
  { key: "location", label: "Location", hint: "Where you went" },
  { key: "activity", label: "Activity", hint: "What you did" },
  { key: "vibe", label: "Vibe", hint: "How it felt between you" },
  { key: "comfort", label: "Comfort", hint: "How safe and at ease you felt" },
];

const SECOND_DATE: { value: ReflectionDraft["secondDate"]; label: string }[] = [
  { value: "yes", label: "Yes" },
  { value: "maybe", label: "Maybe" },
  { value: "no", label: "No" },
];

export function ReflectionForm({
  itineraryId,
  existing,
  onSaved,
}: {
  itineraryId: string;
  existing?: Reflection | null;
  onSaved?: (reflection: Reflection) => void;
}) {
  const [overall, setOverall] = useState(existing?.overall ?? 0);
  const [ratings, setRatings] = useState<Partial<Record<ReflectionAspect, number>>>(
    existing?.ratings ?? {},
  );
  const [secondDate, setSecondDate] = useState<ReflectionDraft["secondDate"] | null>(
    existing?.secondDate ?? null,
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Only the two questions that are genuinely required. Somebody who wants to
  // leave a star and go must be able to.
  const ready = overall > 0 && secondDate !== null;

  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const reflection = await getAdapter().writeReflection(itineraryId, {
        overall,
        ratings,
        secondDate,
        notes: notes.trim(),
      });
      setSaved(true);
      onSaved?.(reflection);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  if (saved) {
    return (
      <div className="space-y-2 rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-4">
        <p className="text-sm text-text">Thank you — that is saved.</p>
        <p className="text-[11px] leading-relaxed text-muted">
          Only you can see it. It is never shown to the person you met, and they
          are never told whether you filled it in.
        </p>
      </div>
    );
  }

  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <h2 className="text-base font-medium text-text">How was it?</h2>
        <p className="text-[11px] leading-relaxed text-muted">
          Only you can see this. It is never shown to the person you met, and
          they are never told whether you filled it in.
        </p>
      </header>

      <Stars
        label="Overall"
        value={overall}
        onChange={setOverall}
        size="large"
      />

      <div className="space-y-3">
        {ASPECTS.map((aspect) => (
          <Stars
            key={aspect.key}
            label={aspect.label}
            hint={aspect.hint}
            value={ratings[aspect.key] ?? 0}
            onChange={(value) =>
              setRatings((current) => ({ ...current, [aspect.key]: value }))
            }
          />
        ))}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-xs font-medium text-text">
          Would you be open to a second date?
        </legend>
        <div className="flex gap-2">
          {SECOND_DATE.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={secondDate === option.value}
              onClick={() => setSecondDate(option.value)}
              className={`flex-1 rounded-full px-3 py-2 text-xs transition-colors ${
                secondDate === option.value
                  ? "bg-accent/25 text-accent-soft"
                  : "bg-white/[0.07] text-text hover:bg-white/[0.12]"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="text-[10px] leading-relaxed text-muted">
          Nobody is told this — not your answer, and not that you were asked.
        </p>
      </fieldset>

      <label className="block space-y-1.5">
        <span className="text-xs font-medium text-text">
          Anything else? <span className="text-muted">(optional)</span>
        </span>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Just for you."
          className="w-full resize-none rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-text placeholder:text-muted/60 focus:border-accent/40 focus:outline-none"
        />
      </label>

      {error ? (
        <p role="alert" className="text-[11px] leading-relaxed text-rose-300">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={submit}
        disabled={!ready || busy}
        className="w-full rounded-full bg-accent px-4 py-3 text-sm font-medium text-cream transition-opacity disabled:opacity-40"
      >
        {busy ? "Saving…" : "Save — just for me"}
      </button>
    </section>
  );
}

function Stars({
  label,
  hint,
  value,
  onChange,
  size = "small",
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (value: number) => void;
  size?: "small" | "large";
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="min-w-0">
        <span
          className={`block ${size === "large" ? "text-sm" : "text-xs"} text-text`}
        >
          {label}
        </span>
        {hint ? <span className="block text-[10px] text-muted">{hint}</span> : null}
      </span>
      <span
        className="flex shrink-0 gap-0.5"
        role="radiogroup"
        aria-label={`${label} rating out of 5`}
      >
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={value === star}
            aria-label={`${star} out of 5`}
            onClick={() => onChange(star)}
            className={`rounded-md px-0.5 transition-colors ${
              size === "large" ? "text-2xl" : "text-lg"
            } ${star <= value ? "text-accent" : "text-white/20 hover:text-white/40"}`}
          >
            ★
          </button>
        ))}
      </span>
    </div>
  );
}
