import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Plus, X } from "lucide-react";

import { getAdapter } from "../api/adapter";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { SettingsPanel } from "../components/SettingsPanel";
import {
  EXCLUDED_ATTRIBUTES,
  KNOWN_INTERESTS,
  KNOWN_TRAITS,
  KNOWN_VALUES,
} from "../api/extract";
import type { ChipKind, Intent, ProfileChip } from "../api/types";
import { intentLabel, intentValue } from "../api/wire";
import { useSpark } from "../store/useSpark";

/**
 * `/profile` — what you told Spark, and how to change it.
 *
 * Onboarding is a conversation you have once. This is the same information as a
 * surface you can come back to, because a profile you can only set by
 * re-running an intake chat is a profile nobody corrects.
 *
 * THE RULES FROM ONBOARDING STILL APPLY HERE, and for the same reasons.
 *
 * INTENT IS NEVER INFERRED. It is chosen from three options in a fixed order
 * with nothing preselected. Changing it is a deliberate act, not something that
 * drifts as a side effect of editing interests.
 *
 * Height and appearance are not ranking fields. A voluntary profile photo is
 * kept behind the mutual-reveal boundary and shown only to lock-ins.
 *
 * IT IS NOT A UI-ONLY PREFERENCES PAGE. Every edit here is written through to
 * the same `Profile` the Match Agent reads, so changing an interest changes the
 * overlap scoring on the next encounter and the grounding of the next date
 * plan. A settings screen whose switches only move pixels is worse than none:
 * it teaches people that saying what they want does not work.
 *
 * WHAT THIS IS STILL HONEST ABOUT: there is no sign-in, so "your" profile is
 * whichever persona this session is following, and it lives as long as the
 * server process does. The screen says so rather than implying an account.
 */
export default function Profile() {
  const navigate = useNavigate();
  const chips = useSpark((s) => s.chips);
  const setChips = useSpark((s) => s.setChips);
  const profilePhoto = useSpark((s) => s.profilePhoto);
  const setProfilePhoto = useSpark((s) => s.setProfilePhoto);
  const [editing, setEditing] = useState<ChipKind | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const uploadPhoto = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setPhotoError("Choose an image file.");
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      setPhotoError("Profile photos must be smaller than 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setProfilePhoto(reader.result);
        setPhotoError(null);
      }
    };
    reader.readAsDataURL(file);
  };

  const has = (kind: ChipKind, label: string) =>
    chips.some((c) => c.kind === kind && c.label === label);

  const toggle = (kind: ChipKind, label: string) => {
    setChips(
      has(kind, label)
        ? chips.filter((c) => !(c.kind === kind && c.label === label))
        : [...chips, { kind, label }],
    );
  };

  /** Intent is single-valued: choosing one replaces any other. */
  const setIntent = (intent: Intent) => {
    setChips([
      ...chips.filter((c) => c.kind !== "intent"),
      { kind: "intent", label: intentLabel(intent) },
    ]);
  };

  const byKind = (kind: ChipKind) => chips.filter((c) => c.kind === kind);
  const intentChip = byKind("intent")[0];

  /**
   * Push edits to the server, so they change matching rather than only the
   * screen.
   *
   * Skipped on the first render: mounting is not an edit, and writing the
   * store's copy back on arrival would overwrite a profile the server already
   * holds with whatever this session happened to have.
   *
   * A failure is SHOWN. Silently dropping a preference is the worst outcome
   * available here — the person believes it took, and Spark keeps matching them
   * on the old answer with no way for them to tell.
   */
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    if (chips.length === 0) return;
    const intent = chips.find((c) => c.kind === "intent");
    void getAdapter()
      .updateProfile({
        ...(intent ? { intents: [intentValue(intent.label)] } : {}),
        interests: chips
          .filter((c) => c.kind === "interest")
          .map((c) => c.label.toLowerCase()),
        values: chips
          .filter((c) => c.kind === "value")
          .map((c) => c.label.toLowerCase()),
        languages: chips
          .filter((c) => c.kind === "language")
          .map((c) => c.label.toLowerCase()),
        personality: chips
          .filter((c) => c.kind === "trait")
          .map((c) => c.label.toLowerCase())
          .join(", "),
      })
      .then(() => setSaveError(null))
      .catch((cause: unknown) =>
        setSaveError(
          cause instanceof Error ? cause.message : String(cause),
        ),
      );
  }, [chips]);

  return (
    <div className={`no-scrollbar h-full overflow-y-auto px-6 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <p className="text-[10px] font-semibold tracking-[0.2em] text-navy/60 uppercase">
          Your profile
        </p>
        <h1 className="mt-1 text-[1.75rem] font-semibold tracking-tight text-text">You</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          What Spark uses to find someone worth three minutes.
        </p>
      </header>

      {chips.length === 0 ? (
        <div className="rounded-card bg-surface px-4 py-5 ring-1 ring-white/[0.06] ring-inset">
          <p className="text-sm leading-relaxed text-text/90">
            You have not set this up yet.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            It is a short conversation, not a form.
          </p>
          <button
            type="button"
            onClick={() => navigate("/onboarding")}
            className="mt-4 w-full rounded-pill bg-accent px-6 py-3.5 text-sm font-medium text-cream transition-opacity hover:opacity-90"
          >
            Set up your profile
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <Section
            title="Profile photo"
            note="Visible only after you and another person both choose to reveal."
          >
            <div className="flex items-center gap-4 rounded-card bg-surface p-4 ring-1 ring-navy/10 ring-inset">
              {profilePhoto ? (
                <img src={profilePhoto} alt="Your profile" className="size-20 rounded-full object-cover ring-2 ring-peach" />
              ) : (
                <div className="grid size-20 shrink-0 place-items-center rounded-full bg-peach/45 text-navy"><Camera size={24} /></div>
              )}
              <div className="min-w-0 flex-1">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-pill bg-navy px-4 py-2.5 text-xs font-semibold text-cream">
                  <Camera size={14} /> {profilePhoto ? "Change photo" : "Upload photo"}
                  <input type="file" accept="image/*" className="sr-only" onChange={(event) => uploadPhoto(event.target.files?.[0])} />
                </label>
                {profilePhoto ? <button type="button" onClick={() => setProfilePhoto(null)} className="mt-2 block text-[11px] font-medium text-clay">Remove photo</button> : null}
                <p className="mt-2 text-[10px] leading-relaxed text-muted">JPG, PNG or WebP · up to 4 MB</p>
              </div>
            </div>
            {photoError ? <p role="alert" className="mt-2 text-xs text-clay">{photoError}</p> : null}
          </Section>

          {/* --- what you are here for ------------------------------------ */}
          <Section
            title="What you are here for"
            note="Only ever what you have said. Spark never reads this from your tone."
          >
            <div className="flex flex-col gap-2">
              {(
                [
                  "partner_long_term",
                  "partner_short_term",
                  "friends",
                ] as Intent[]
              ).map((intent) => {
                const label = intentLabel(intent);
                const active = intentChip?.label === label;
                return (
                  <button
                    key={intent}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setIntent(intent)}
                    className={`w-full rounded-pill px-5 py-3 text-left text-[15px] ring-1 ring-inset transition-colors ${
                      active
                        ? "bg-accent/25 text-accent-soft ring-accent/30"
                        : "bg-surface text-text ring-white/[0.06] hover:bg-white/[0.07]"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </Section>

          {/* --- personality, interests and values ------------------------ */}
          <EditableChips
            title="Characteristics"
            options={[...KNOWN_TRAITS]}
            chips={byKind("trait")}
            editing={editing === "trait"}
            onToggleEdit={() =>
              setEditing(editing === "trait" ? null : "trait")
            }
            onToggle={(label) => toggle("trait", label)}
            has={(label) => has("trait", label)}
            allowCustom
          />

          <EditableChips
            title="Interests"
            options={[...KNOWN_INTERESTS]}
            chips={byKind("interest")}
            editing={editing === "interest"}
            onToggleEdit={() =>
              setEditing(editing === "interest" ? null : "interest")
            }
            onToggle={(label) => toggle("interest", label)}
            has={(label) => has("interest", label)}
            allowCustom
          />

          <EditableChips
            title="What matters to you"
            options={[...KNOWN_VALUES]}
            chips={byKind("value")}
            editing={editing === "value"}
            onToggleEdit={() => setEditing(editing === "value" ? null : "value")}
            onToggle={(label) => toggle("value", label)}
            has={(label) => has("value", label)}
            allowCustom
          />

          {/* Availability is editable, and lives with the other settings that
              genuinely change what the system does — see `SettingsPanel`. */}
          <EditableChips
            title="Languages"
            options={[
              "english",
              "mandarin",
              "malay",
              "tamil",
              "cantonese",
              "hokkien",
            ]}
            chips={byKind("language")}
            editing={editing === "language"}
            onToggleEdit={() =>
              setEditing(editing === "language" ? null : "language")
            }
            onToggle={(label) => toggle("language", label)}
            has={(label) => has("language", label)}
            allowCustom
          />

          <Section
            title="Not here, on purpose"
            note="Spark has no height or appearance-ranking field. Your photo is never shown before a mutual reveal."
          >
            <></>
          </Section>

          <SettingsPanel />

          <button
            type="button"
            onClick={() => navigate("/onboarding")}
            className="w-full rounded-pill bg-white/[0.06] px-6 py-3 text-sm text-text transition-colors hover:bg-white/[0.1]"
          >
            Go through the questions again
          </button>

          {saveError ? (
            <p role="alert" className="text-[11px] leading-relaxed text-rose-300">
              That change was not saved: {saveError}
            </p>
          ) : null}

          {/* Honest about where this lives. */}
          <p className="text-center text-[11px] leading-relaxed text-muted/70">
            These preferences change how Spark matches and plans for you. There
            is no sign-in yet, so they last as long as the session does.
          </p>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2 text-[10px] tracking-[0.18em] text-muted uppercase">
        {title}
      </h2>
      {note ? (
        <p className="mb-2.5 text-xs leading-relaxed text-muted/80">{note}</p>
      ) : null}
      {children}
    </section>
  );
}

function ChipRow({ chips }: { chips: ProfileChip[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {chips.map((chip) => (
        <span
          key={`${chip.kind}:${chip.label}`}
          className="rounded-pill bg-cream px-3 py-1.5 text-[13px] text-text/90 ring-1 ring-navy/15 ring-inset"
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}

/**
 * A section you can open and edit.
 *
 * The options are the FIXED vocabulary from `extract.ts` — the same list the
 * Onboarding Agent extracts against. That is what keeps the two in step: a
 * profile edited here contains exactly the things an intake conversation could
 * have produced, and nothing a free-text box would have let in.
 */
function EditableChips({
  title,
  options,
  chips,
  editing,
  onToggleEdit,
  onToggle,
  has,
  allowCustom = false,
}: {
  title: string;
  options: string[];
  chips: ProfileChip[];
  editing: boolean;
  onToggleEdit: () => void;
  onToggle: (label: string) => void;
  has: (label: string) => boolean;
  allowCustom?: boolean;
}) {
  const titleCase = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
  const [customValue, setCustomValue] = useState("");
  const [customError, setCustomError] = useState<string | null>(null);
  const standardLabels = new Set(options.map(titleCase));
  const customChips = chips.filter((chip) => !standardLabels.has(chip.label));

  const addCustom = () => {
    const clean = customValue.trim().replace(/\s+/g, " ");
    if (!clean) return;
    if (EXCLUDED_ATTRIBUTES.test(clean)) {
      setCustomError(
        "Spark does not collect appearance or body characteristics.",
      );
      return;
    }

    const label = titleCase(clean.toLowerCase()).slice(0, 40);
    if (!has(label)) onToggle(label);
    setCustomValue("");
    setCustomError(null);
  };

  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[10px] tracking-[0.18em] text-muted uppercase">
          {title}
        </h2>
        <button
          type="button"
          onClick={onToggleEdit}
          className="text-[11px] text-muted underline-offset-2 hover:text-text hover:underline"
        >
          {editing ? "Done" : "Edit"}
        </button>
      </div>

      {editing ? (
        <div className="rounded-card bg-cream/75 p-3.5 ring-1 ring-navy/10 ring-inset">
          <div className="flex flex-wrap gap-2">
            {options.map((option) => {
              const label = titleCase(option);
              const active = has(label);
              return (
                <button
                  key={option}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onToggle(label)}
                  className={`rounded-pill px-3 py-1.5 text-[13px] ring-1 ring-inset transition-colors ${
                    active
                      ? "bg-navy text-cream ring-navy"
                      : "bg-peach/35 text-text/80 ring-navy/10 hover:bg-peach/60"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {allowCustom ? (
            <div className="mt-4 border-t border-navy/10 pt-3">
              {customChips.length > 0 ? (
                <div className="mb-3 flex flex-wrap gap-2" aria-label={`Custom ${title.toLowerCase()}`}>
                  {customChips.map((chip) => (
                    <button
                      key={`${chip.kind}:${chip.label}`}
                      type="button"
                      onClick={() => onToggle(chip.label)}
                      aria-label={`Remove ${chip.label}`}
                      className="inline-flex items-center gap-1.5 rounded-pill bg-navy px-3 py-1.5 text-[12px] text-cream"
                    >
                      {chip.label}
                      <X size={12} aria-hidden="true" />
                    </button>
                  ))}
                </div>
              ) : null}
              <label
                htmlFor={`custom-${title.toLowerCase().replace(/\s+/g, "-")}`}
                className="text-[10px] font-semibold tracking-[0.16em] text-navy/65 uppercase"
              >
                Others
              </label>
              <div className="mt-2 flex gap-2">
                <input
                  id={`custom-${title.toLowerCase().replace(/\s+/g, "-")}`}
                  type="text"
                  maxLength={40}
                  value={customValue}
                  onChange={(event) => {
                    setCustomValue(event.target.value);
                    if (customError) setCustomError(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addCustom();
                    }
                  }}
                  placeholder={
                    title === "Interests"
                      ? "Add another interest"
                      : title === "Languages"
                        ? "Add another language"
                        : title === "What matters to you"
                          ? "Add another value"
                      : "Add a characteristic"
                  }
                  className="min-w-0 flex-1 rounded-pill border border-navy/15 bg-surface px-4 py-2.5 text-sm text-text placeholder:text-muted/60 focus:border-navy/40 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={addCustom}
                  disabled={!customValue.trim()}
                  aria-label={`Add custom ${title.toLowerCase()}`}
                  className="grid size-10 shrink-0 place-items-center rounded-full bg-navy text-cream transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <Plus size={17} aria-hidden="true" />
                </button>
              </div>
              {customError ? (
                <p role="alert" className="mt-2 flex items-center gap-1.5 text-[11px] leading-relaxed text-clay">
                  <X size={12} aria-hidden="true" />
                  {customError}
                </p>
              ) : (
                <p className="mt-2 text-[10px] leading-relaxed text-muted/75">
                  Add your own words. These are saved with the rest of your profile.
                </p>
              )}
            </div>
          ) : null}
        </div>
      ) : chips.length > 0 ? (
        <ChipRow chips={chips} />
      ) : (
        <p className="text-xs text-muted/70">
          Nothing yet — press Edit, or go through the questions.
        </p>
      )}
    </section>
  );
}
