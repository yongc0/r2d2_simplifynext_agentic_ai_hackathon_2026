import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getAdapter } from "../api/adapter";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { SettingsPanel } from "../components/SettingsPanel";
import { KNOWN_INTERESTS, KNOWN_TRAITS, KNOWN_VALUES } from "../api/extract";
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
 * NO HEIGHT, APPEARANCE OR PHOTO — invariant 9.5. There is no such field, no
 * upload, and `ChipKind` has no member one could be rendered as. The interest
 * list below is the fixed vocabulary from `extract.ts`, so a physical attribute
 * cannot be typed in either: there is nothing to type into.
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
  const [editing, setEditing] = useState<ChipKind | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

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
    <div className={`no-scrollbar h-full overflow-y-auto px-6 pt-16 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <h1 className="text-2xl font-medium tracking-tight text-text">You</h1>
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
            className="mt-4 w-full rounded-pill bg-accent px-6 py-3.5 text-sm font-medium text-text transition-opacity hover:opacity-90"
          >
            Set up your profile
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
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
            title="How you describe yourself"
            options={[...KNOWN_TRAITS]}
            chips={byKind("trait")}
            editing={editing === "trait"}
            onToggleEdit={() =>
              setEditing(editing === "trait" ? null : "trait")
            }
            onToggle={(label) => toggle("trait", label)}
            has={(label) => has("trait", label)}
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
          />

          <EditableChips
            title="What matters to you"
            options={[...KNOWN_VALUES]}
            chips={byKind("value")}
            editing={editing === "value"}
            onToggleEdit={() => setEditing(editing === "value" ? null : "value")}
            onToggle={(label) => toggle("value", label)}
            has={(label) => has("value", label)}
          />

          {/* Availability is editable, and lives with the other settings that
              genuinely change what the system does — see `SettingsPanel`. */}
          {byKind("language").length > 0 ? (
            <Section title="Languages">
              <ChipRow chips={byKind("language")} />
            </Section>
          ) : null}

          <Section
            title="Not here, on purpose"
            note="Spark has no height, photo or appearance field, and will not add one. Removing judgement-by-photograph is the point of the product."
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
          className="rounded-pill bg-white/[0.06] px-3 py-1.5 text-[13px] text-text/90 ring-1 ring-white/10 ring-inset"
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
}: {
  title: string;
  options: string[];
  chips: ProfileChip[];
  editing: boolean;
  onToggleEdit: () => void;
  onToggle: (label: string) => void;
  has: (label: string) => boolean;
}) {
  const titleCase = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

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
                    ? "bg-accent/25 text-accent-soft ring-accent/30"
                    : "bg-white/[0.04] text-text/80 ring-white/[0.08] hover:bg-white/[0.08]"
                }`}
              >
                {label}
              </button>
            );
          })}
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
