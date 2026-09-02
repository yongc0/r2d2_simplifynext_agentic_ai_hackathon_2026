import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { KNOWN_INTERESTS, KNOWN_TRAITS, KNOWN_VALUES } from "../api/extract";
import type { Intent, ProfileChip } from "../api/types";
import { intentLabel } from "../api/wire";
import { useSpark } from "../store/useSpark";

interface TestProfile {
  id: string;
  label: string;
  intent: Intent;
  traits: string[];
  interests: string[];
  values: string[];
  availability: string[];
}

const STORAGE_KEY = "spark.demo.test-profiles.v1";

const DEFAULT_PROFILES: TestProfile[] = [
  {
    id: "curious-regular",
    label: "Curious regular",
    intent: "partner_long_term",
    traits: ["thoughtful", "curious"],
    interests: ["coffee", "reading", "photography"],
    values: ["honesty", "curiosity"],
    availability: ["evening"],
  },
  {
    id: "social-explorer",
    label: "Social explorer",
    intent: "friends",
    traits: ["outgoing", "adventurous", "playful"],
    interests: ["climbing", "live music", "hiking"],
    values: ["adventure", "kindness"],
    availability: ["afternoon", "night"],
  },
];

const INTENTS: Intent[] = [
  "partner_long_term",
  "partner_short_term",
  "friends",
];

const AVAILABILITY = [
  ["early_morning", "Early morning"],
  ["morning", "Morning"],
  ["midday", "Midday"],
  ["afternoon", "Afternoon"],
  ["evening", "Evening"],
  ["night", "Night"],
] as const;

function readProfiles(): TestProfile[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return DEFAULT_PROFILES;
    const parsed = JSON.parse(saved) as unknown;
    return Array.isArray(parsed) ? (parsed as TestProfile[]) : DEFAULT_PROFILES;
  } catch {
    return DEFAULT_PROFILES;
  }
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function profileChips(profile: TestProfile): ProfileChip[] {
  return [
    { kind: "intent", label: intentLabel(profile.intent) },
    ...profile.traits.map((label) => ({ kind: "trait" as const, label: titleCase(label) })),
    ...profile.interests.map((label) => ({ kind: "interest" as const, label: titleCase(label) })),
    ...profile.values.map((label) => ({ kind: "value" as const, label: titleCase(label) })),
    ...profile.availability.map((bucket) => ({
      kind: "availability" as const,
      label: AVAILABILITY.find(([value]) => value === bucket)?.[1] ?? titleCase(bucket),
    })),
    { kind: "language", label: "English" },
  ];
}

export default function AdminProfiles() {
  const navigate = useNavigate();
  const setChips = useSpark((state) => state.setChips);
  const [profiles, setProfiles] = useState<TestProfile[]>(readProfiles);
  const [activeId, setActiveId] = useState<string | null>(() =>
    localStorage.getItem(`${STORAGE_KEY}.active`),
  );
  const [label, setLabel] = useState("");
  const [intent, setIntent] = useState<Intent>("friends");
  const [traits, setTraits] = useState<string[]>([]);
  const [interests, setInterests] = useState<string[]>([]);
  const [values, setValues] = useState<string[]>([]);
  const [availability, setAvailability] = useState<string[]>(["evening"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const persist = (next: TestProfile[]) => {
    setProfiles(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };

  const addProfile = () => {
    const cleanLabel = label.trim().slice(0, 48);
    if (!cleanLabel) {
      setError("Give this test profile a short label.");
      return;
    }
    const id = `${cleanLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-${Date.now()}`;
    persist([
      ...profiles,
      {
        id,
        label: cleanLabel,
        intent,
        traits,
        interests,
        values,
        availability,
      },
    ]);
    setLabel("");
    setTraits([]);
    setInterests([]);
    setValues([]);
    setAvailability(["evening"]);
    setError(null);
  };

  const useProfile = async (profile: TestProfile) => {
    setBusy(true);
    setError(null);
    try {
      await getAdapter().updateProfile({
        intents: [profile.intent],
        personality: profile.traits.join(", "),
        interests: profile.interests,
        values: profile.values,
        languages: ["English"],
        availabilityWindow: profile.availability,
      });
      setChips(profileChips(profile));
      setActiveId(profile.id);
      localStorage.setItem(`${STORAGE_KEY}.active`, profile.id);
      navigate("/profile");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const removeProfile = (id: string) => {
    persist(profiles.filter((profile) => profile.id !== id));
    if (activeId === id) {
      setActiveId(null);
      localStorage.removeItem(`${STORAGE_KEY}.active`);
    }
  };

  return (
    <div className="no-scrollbar h-full overflow-y-auto px-5 pt-12 pb-10">
      <header className="mb-5">
        <div className="mb-3 flex items-center justify-between">
          <span className="rounded-pill bg-amber-400/10 px-3 py-1 text-[10px] font-medium tracking-[0.14em] text-amber-200 uppercase ring-1 ring-amber-400/20 ring-inset">
            Demo only
          </span>
          <button
            type="button"
            onClick={() => navigate("/home")}
            className="text-xs text-muted hover:text-text"
          >
            Close
          </button>
        </div>
        <h1 className="text-2xl font-medium tracking-tight text-text">Profile Lab</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Build synthetic profile presets and switch between them while testing.
        </p>
        <p className="mt-2 rounded-card bg-amber-400/[0.06] px-3 py-2.5 text-[11px] leading-relaxed text-amber-100/75 ring-1 ring-amber-400/10 ring-inset">
          Presets stay in this browser. This is not an authenticated admin
          system and must not contain real personal data.
        </p>
      </header>

      <section className="mb-7" aria-labelledby="saved-test-profiles">
        <h2 id="saved-test-profiles" className="mb-2 text-[10px] tracking-[0.18em] text-muted uppercase">
          Saved test profiles
        </h2>
        <div className="flex flex-col gap-2.5">
          {profiles.map((profile) => (
            <article
              key={profile.id}
              className="rounded-card bg-surface p-4 ring-1 ring-white/[0.06] ring-inset"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-medium text-text">{profile.label}</h3>
                  <p className="mt-1 text-xs text-muted">{intentLabel(profile.intent)}</p>
                </div>
                {activeId === profile.id ? (
                  <span className="rounded-pill bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-200">
                    Active
                  </span>
                ) : null}
              </div>
              <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted/80">
                {[...profile.traits, ...profile.interests, ...profile.availability]
                  .map(titleCase)
                  .join(" · ") || "No optional details"}
              </p>
              <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => useProfile(profile)}
                  className="rounded-pill bg-accent px-4 py-2.5 text-sm font-medium text-cream disabled:opacity-40"
                >
                  Use {profile.label}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => removeProfile(profile.id)}
                  aria-label={`Remove ${profile.label}`}
                  className="rounded-pill bg-white/[0.05] px-4 py-2.5 text-xs text-muted hover:text-text disabled:opacity-40"
                >
                  Remove
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section aria-labelledby="create-test-profile">
        <h2 id="create-test-profile" className="mb-3 text-[10px] tracking-[0.18em] text-muted uppercase">
          Create test profile
        </h2>
        <div className="flex flex-col gap-5 rounded-card bg-surface/60 p-4 ring-1 ring-white/[0.06] ring-inset">
          <label className="block">
            <span className="mb-1.5 block text-xs text-muted">Preset name</span>
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              maxLength={48}
              placeholder="e.g. Weekend tester"
              className="w-full rounded-xl bg-bg px-4 py-3 text-sm text-text placeholder:text-muted/45 focus:outline-none focus:ring-1 focus:ring-accent/50"
            />
          </label>

          <ChoiceGroup title="Intent">
            {INTENTS.map((option) => (
              <Choice
                key={option}
                label={intentLabel(option)}
                active={intent === option}
                onClick={() => setIntent(option)}
              />
            ))}
          </ChoiceGroup>

          <ChoiceGroup title="Traits">
            {KNOWN_TRAITS.map((option) => (
              <Choice
                key={option}
                label={titleCase(option)}
                active={traits.includes(option)}
                onClick={() => setTraits(toggle(traits, option, 5))}
              />
            ))}
          </ChoiceGroup>

          <ChoiceGroup title="Interests">
            {KNOWN_INTERESTS.map((option) => (
              <Choice
                key={option}
                label={titleCase(option)}
                active={interests.includes(option)}
                onClick={() => setInterests(toggle(interests, option, 8))}
              />
            ))}
          </ChoiceGroup>

          <ChoiceGroup title="Values">
            {KNOWN_VALUES.map((option) => (
              <Choice
                key={option}
                label={titleCase(option)}
                active={values.includes(option)}
                onClick={() => setValues(toggle(values, option, 5))}
              />
            ))}
          </ChoiceGroup>

          <ChoiceGroup title="Availability">
            {AVAILABILITY.map(([value, optionLabel]) => (
              <Choice
                key={value}
                label={optionLabel}
                active={availability.includes(value)}
                onClick={() => setAvailability(toggle(availability, value, 3))}
              />
            ))}
          </ChoiceGroup>

          <button
            type="button"
            onClick={addProfile}
            className="w-full rounded-pill bg-accent px-5 py-3.5 text-sm font-medium text-cream transition-opacity hover:opacity-90"
          >
            Save test profile
          </button>
        </div>
      </section>

      {error ? (
        <p role="alert" className="mt-3 text-xs leading-relaxed text-rose-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function toggle(values: string[], value: string, limit: number): string[] {
  if (values.includes(value)) return values.filter((item) => item !== value);
  return values.length < limit ? [...values, value] : values;
}

function ChoiceGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs text-muted">{title}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

function Choice({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-pill px-3 py-1.5 text-xs ring-1 ring-inset transition-colors ${
        active
          ? "bg-accent/25 text-accent-soft ring-accent/30"
          : "bg-white/[0.04] text-text/80 ring-white/[0.08] hover:bg-white/[0.08]"
      }`}
    >
      {label}
    </button>
  );
}
