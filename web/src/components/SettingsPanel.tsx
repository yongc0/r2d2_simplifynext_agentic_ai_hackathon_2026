import { useEffect, useState } from "react";

import { getAdapter } from "../api/adapter";
import type { EditableProfile, Settings } from "../api/types";

/**
 * The switches, and when you are reachable.
 *
 * WHY "RECEIVE CALLS FROM SPARK" IS FIRST AND WHY IT IS NOT A DISPLAY SETTING
 *
 * The daily call IS the product, so switching it off is the biggest thing a
 * person can do here and it deserves the top of the screen and a plain warning
 * rather than a buried toggle.
 *
 * It is enforced in `spark-voice.connect_call` — the one place in the whole
 * system a call can be created — in the same shape as the mutual-consent flag:
 * the bridge is HANDED permission and refuses without it. Hiding the call UI
 * alone would leave a code path intact that still rings somebody who asked not
 * to be rung, and that is the difference between a preference and a decoration.
 *
 * A calls-disabled encounter ends as ABANDONED, which is the same terminal
 * state as a no-show. That is deliberate: nothing the other person can observe
 * distinguishes "they turned calls off" from "they did not pick up".
 *
 * AVAILABILITY IS NOT COSMETIC EITHER. It is written to the same `Profile` the
 * Match Agent reads, so it decides which encounter slots you can be offered in
 * at all. The choices are the times you have actually been out in, because a
 * window nobody is ever free in would quietly remove you from every pool.
 */

const SWITCHES: {
  key: keyof Settings;
  label: string;
  detail: string;
}[] = [
  {
    key: "allowCalls",
    label: "Receive calls from Spark",
    detail:
      "Off means no calls are placed to you at all — not hidden, not queued. " +
      "Nobody is told why; an encounter simply ends the way one does when " +
      "somebody does not pick up.",
  },
  {
    key: "allowDateSuggestions",
    label: "Suggest dates",
    detail:
      "Plans for people you have already met. Off for either of you means " +
      "neither gets suggestions for that connection.",
  },
  {
    key: "allowContinuityNotes",
    label: "Remember what you talked about",
    detail:
      "Short notes from your own calls, so a later one can pick up where it " +
      "left off. Yours only, and they expire.",
  },
  {
    key: "allowConversationPrompts",
    label: "Offer things to talk about",
    detail:
      "A prompt or two during a call, grounded in something you both " +
      "actually said. Off by default.",
  },
];

const BUCKET_LABEL: Record<string, string> = {
  early_morning: "Early morning",
  morning: "Morning",
  midday: "Midday",
  afternoon: "Afternoon",
  evening: "Evening",
  night: "Night",
};

export function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [profile, setProfile] = useState<EditableProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const adapter = getAdapter();
        const [nextSettings, nextProfile] = await Promise.all([
          adapter.getSettings(),
          adapter.getProfile(),
        ]);
        if (cancelled) return;
        setSettings(nextSettings);
        setProfile(nextProfile);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const flip = async (key: keyof Settings) => {
    if (!settings) return;
    setBusy(true);
    setError(null);
    // Optimistic, then corrected by the server's answer. A switch that lags a
    // round trip reads as broken and gets tapped twice.
    const optimistic = { ...settings, [key]: !settings[key] };
    setSettings(optimistic);
    try {
      setSettings(await getAdapter().updateSettings({ [key]: optimistic[key] }));
    } catch (cause) {
      setSettings(settings);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const toggleBucket = async (bucket: string) => {
    if (!profile) return;
    const next = profile.availabilityWindow.includes(bucket)
      ? profile.availabilityWindow.filter((b) => b !== bucket)
      : [...profile.availabilityWindow, bucket];
    setBusy(true);
    setError(null);
    try {
      setProfile(await getAdapter().updateProfile({ availabilityWindow: next }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  if (error && !settings) {
    return (
      <p role="alert" className="text-xs leading-relaxed text-rose-300">
        {error}
      </p>
    );
  }
  if (!settings) {
    return <p className="text-xs text-muted">Loading your settings…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h2 className="mb-3 text-xs tracking-[0.18em] text-muted uppercase">
          Settings
        </h2>
        <div className="flex flex-col gap-2">
          {SWITCHES.map((item) => (
            <Switch
              key={item.key}
              label={item.label}
              detail={item.detail}
              on={settings[item.key]}
              busy={busy}
              onFlip={() => flip(item.key)}
            />
          ))}
        </div>
        {!settings.allowCalls ? (
          <p className="mt-2 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-100/80">
            Calls are off. Spark will not place any, and you will not be offered
            an encounter until you turn them back on.
          </p>
        ) : null}
      </section>

      {profile ? (
        <section>
          <h2 className="mb-1 text-xs tracking-[0.18em] text-muted uppercase">
            When you are usually free
          </h2>
          <p className="mb-3 text-[11px] leading-relaxed text-muted">
            This decides when you can be offered an encounter, not just what
            this screen says.
          </p>
          <div className="flex flex-wrap gap-2">
            {profile.knownBuckets.map((bucket) => {
              const active = profile.availabilityWindow.includes(bucket);
              return (
                <button
                  key={bucket}
                  type="button"
                  aria-pressed={active}
                  disabled={busy}
                  onClick={() => toggleBucket(bucket)}
                  className={`rounded-pill px-3 py-1.5 text-[13px] ring-1 ring-inset transition-colors disabled:opacity-50 ${
                    active
                      ? "bg-accent/25 text-accent-soft ring-accent/30"
                      : "bg-white/[0.04] text-text/80 ring-white/[0.08] hover:bg-white/[0.08]"
                  }`}
                >
                  {BUCKET_LABEL[bucket] ?? bucket}
                </button>
              );
            })}
          </div>
          {profile.availabilityWindow.length === 0 ? (
            <p className="mt-2 text-[11px] font-medium leading-relaxed text-amber-900">
              With no times selected there is no slot you can be matched in.
            </p>
          ) : null}
        </section>
      ) : null}

      {error ? (
        <p role="alert" className="text-[11px] leading-relaxed text-rose-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Switch({
  label,
  detail,
  on,
  busy,
  onFlip,
}: {
  label: string;
  detail: string;
  on: boolean;
  busy: boolean;
  onFlip: () => void;
}) {
  return (
    <div className="rounded-card bg-surface px-4 py-3 ring-1 ring-white/[0.06] ring-inset">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        disabled={busy}
        onClick={onFlip}
        className="flex w-full items-center justify-between gap-3 text-left disabled:opacity-60"
      >
        <span className="text-sm text-text">{label}</span>
        <span
          aria-hidden
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            on ? "bg-accent/70" : "bg-white/[0.12]"
          }`}
        >
          <span
            className={`absolute top-1 h-4 w-4 rounded-full bg-white transition-all ${
              on ? "left-6" : "left-1"
            }`}
          />
        </span>
      </button>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{detail}</p>
    </div>
  );
}
