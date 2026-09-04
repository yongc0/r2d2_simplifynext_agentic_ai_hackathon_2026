import type { EditableProfile, ProfileChip } from "./types";
import { intentValue } from "./wire";

const PROFILE_CACHE_KEY = "spark.profile-chips.v1";
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

/**
 * Remove the cache used by older builds. A profile now deliberately lasts only
 * for the current page session so every refresh starts with profile setup.
 */
function clearCachedProfileChips(): void {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(PROFILE_CACHE_KEY);
}

/** Reset profile setup at browser bootstrap, before React reads the route. */
export function beginFreshProfileSession(): void {
  clearCachedProfileChips();
  if (typeof window === "undefined" || window.location.pathname === "/onboarding") {
    return;
  }
  window.history.replaceState(
    window.history.state,
    "",
    `/onboarding${window.location.search}`,
  );
}
