import type { EditableProfile, Intent, ProfileChip } from "./types";
import { intentLabel, intentValue } from "./wire";

const PROFILE_CACHE_KEY = "spark.profile-chips.v1";
const CHIP_KINDS = new Set<ProfileChip["kind"]>([
  "intent",
  "trait",
  "interest",
  "value",
  "availability",
  "language",
]);

/** The exact matchable profile payload represented by the visible chips. */
export function profilePatchFromChips(
  chips: ProfileChip[],
): Partial<EditableProfile> {
  const labels = (kind: ProfileChip["kind"]) =>
    chips
      .filter((chip) => chip.kind === kind)
      .map((chip) => chip.label.trim().toLowerCase())
      .filter(Boolean);
  const intents = chips
    .filter((chip) => chip.kind === "intent")
    .map((chip) => intentValue(chip.label));

  return {
    ...(intents.length > 0 ? { intents } : {}),
    interests: labels("interest"),
    values: labels("value"),
    personality: labels("trait").join(", "),
    languages: labels("language"),
  };
}

/** Turn the server's authoritative profile back into the You screen's chips. */
export function chipsFromProfile(profile: EditableProfile): ProfileChip[] {
  const chips: ProfileChip[] = [];
  const push = (kind: ProfileChip["kind"], labels: string[]) => {
    for (const label of labels) {
      const clean = label.trim();
      if (!clean) continue;
      const display = clean
        .split(/\s+/)
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");
      if (!chips.some((chip) => chip.kind === kind && chip.label === display)) {
        chips.push({ kind, label: display });
      }
    }
  };

  for (const value of profile.intents) {
    if (["partner_long_term", "partner_short_term", "friends"].includes(value)) {
      chips.push({ kind: "intent", label: intentLabel(value as Intent) });
    }
  }
  push("trait", profile.personality.split(/[,;]+/));
  push("interest", profile.interests);
  push("value", profile.values);
  push("availability", profile.availabilityWindow);
  push("language", profile.languages);
  return chips;
}

/**
 * A device cache for the completed profile, never the HTTP source of truth.
 * It restores the offline demo and gives the connected app something to render
 * while `GET /profile` revalidates after a refresh.
 */
export function cacheProfileChips(chips: ProfileChip[]): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(chips));
}

export function readCachedProfileChips(): ProfileChip[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PROFILE_CACHE_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(
      (chip): chip is ProfileChip =>
        typeof chip === "object" &&
        chip !== null &&
        "kind" in chip &&
        CHIP_KINDS.has(chip.kind as ProfileChip["kind"]) &&
        "label" in chip &&
        typeof chip.label === "string" &&
        chip.label.trim().length > 0,
    );
  } catch {
    return [];
  }
}
