/**
 * The offline mirror of `spark/src/agents/onboarding.py`.
 *
 * `MockAdapter` has to extract a profile with no backend and no key, so this
 * reimplements the agent's DETERMINISTIC path — the same one the Python agent
 * falls back to when no provider is configured (`_deterministic_extract`).
 *
 * WHAT IS COPIED HERE AND WHY IT MATTERS
 *
 * The keyword lists below are duplicated from the Python. Duplication is a
 * drift risk, so it is not left to good intentions:
 * `spark/tests/test_wire_contract.py` reads this file and fails if the two
 * disagree. If you add an interest on one side, that test tells you about the
 * other.
 *
 * THE RULE THAT IS NOT A KEYWORD LIST
 *
 * From ARCHITECTURE §13.1, restated at the top of the Python agent:
 *
 *     Intent is never inferred from tone. If the user did not name it, it is
 *     not set.
 *
 * That is a safety rule, not a data-quality one — reading "casual" into a warm
 * sentence puts two people in front of each other under a misunderstanding
 * neither agreed to. So `namedIntents()` matches literal phrases and nothing
 * else, and the screen ASKS when it comes back empty. There is deliberately no
 * cleverness here to be tempted by.
 *
 * Physical attributes are stripped on the way through (invariant 9.5). There is
 * no field for a height and there will not be one.
 */

import type { Intent, ProfileChip } from "./types";
import { intentLabel } from "./wire";

// ---------------------------------------------------------------------------
// The lists. Mirrored from spark/src/agents/onboarding.py — see the note above.
// ---------------------------------------------------------------------------

/** Phrases that NAME an intent. This list IS the definition of "they said it". */
const INTENT_PHRASES: [RegExp, Intent][] = [
  [/\blong[- ]term\b/i, "partner_long_term"],
  [/\bsomething serious\b/i, "partner_long_term"],
  [/\bsettle down\b/i, "partner_long_term"],
  [/\blife partner\b/i, "partner_long_term"],
  [/\bmarriage\b/i, "partner_long_term"],
  [/\bshort[- ]term\b/i, "partner_short_term"],
  [/\bcasual\b/i, "partner_short_term"],
  [/\bnothing serious\b/i, "partner_short_term"],
  [/\bsee where it goes\b/i, "partner_short_term"],
  [/\b(?:make|meet|new) friends\b/i, "friends"],
  [/\bfriendship\b/i, "friends"],
  [/\bplatonic\b/i, "friends"],
];

export const KNOWN_INTERESTS = [
  "climbing", "running", "cooking", "film", "live music", "board games",
  "cycling", "photography", "reading", "hiking", "coffee", "pottery",
  "swimming", "languages", "volunteering", "gardening", "chess", "baking",
  "football", "yoga", "birdwatching", "woodwork",
] as const;

export const KNOWN_VALUES = [
  "honesty", "ambition", "family", "independence", "humour", "stability",
  "adventure", "kindness", "curiosity", "faith",
] as const;

/** Optional shortcuts for the opening question. Free text remains available. */
export const KNOWN_TRAITS = [
  "outgoing", "thoughtful", "adventurous", "calm", "curious", "creative",
  "playful", "optimistic", "kind", "independent", "ambitious", "easygoing",
  "happy",
] as const;

const BUCKET_PHRASES: [RegExp, string][] = [
  [/\bearly morning|before work|dawn\b/i, "early_morning"],
  [/\bmornings?\b/i, "morning"],
  [/\blunch|midday|noon\b/i, "midday"],
  [/\bafternoons?\b/i, "afternoon"],
  [/\bevenings?|after work\b/i, "evening"],
  [/\bnights?|late\b/i, "night"],
];

const LANGUAGES = [
  "english", "mandarin", "malay", "tamil", "cantonese", "hokkien",
] as const;

/**
 * Physical attributes — INVARIANT 9.5.
 *
 * Stripped whether the person volunteered them or a model echoed them back. A
 * product whose central claim is removing judgement-by-photograph has nowhere
 * to put them, so nothing that matches this ever becomes a chip.
 */
export const EXCLUDED_ATTRIBUTES =
  /\b(?:height|tall|short|slim|fit|athletic|attractive|good[- ]looking|pretty|handsome|photo|selfie|picture|body|weight|kg|cm)\b/i;

// ---------------------------------------------------------------------------
// Extraction
// ---------------------------------------------------------------------------

/** The intents this text actually NAMES, in a stable order, deduplicated. */
export function namedIntents(transcript: string): Intent[] {
  const found: Intent[] = [];
  for (const [pattern, intent] of INTENT_PHRASES) {
    if (pattern.test(transcript) && !found.includes(intent)) found.push(intent);
  }
  return found;
}

export interface Extraction {
  intents: Intent[];
  traits: string[];
  interests: string[];
  values: string[];
  availability: string[];
  languages: string[];
  /** What still has to be asked about. Mirrors `OnboardingExtraction.unresolved`. */
  unresolved: string[];
}

/**
 * Read a cumulative transcript into a structured extraction.
 *
 * Cumulative, not per-message, exactly like `OnboardingAgent.extract(user_id,
 * transcript)`: someone who names their interests in turn one and their
 * availability in turn three has said both things, and an extractor with no
 * memory would keep asking about the first.
 */
export function extractFromTranscript(transcript: string): Extraction {
  // Attributes are removed BEFORE matching, not filtered afterwards, so a
  // sentence mentioning one cannot contribute it through some other list.
  const lowered = transcript.toLowerCase().replace(EXCLUDED_ATTRIBUTES, " ");

  const has = (term: string) =>
    new RegExp(`\\b${term.replace(/ /g, "\\s+")}\\b`, "i").test(lowered);

  const interests = KNOWN_INTERESTS.filter(has);
  const values = KNOWN_VALUES.filter(has);
  const traits = KNOWN_TRAITS.filter(has);
  const availability = [
    ...new Set(
      BUCKET_PHRASES.filter(([p]) => p.test(lowered)).map(([, b]) => b),
    ),
  ];
  const languages = LANGUAGES.filter((l) => lowered.includes(l));
  const intents = namedIntents(transcript);

  const unresolved: string[] = [];
  if (intents.length === 0) unresolved.push("intent");
  if (interests.length === 0) unresolved.push("interests");
  if (traits.length === 0) unresolved.push("characteristics");
  if (values.length === 0) unresolved.push("values");
  if (languages.length === 0) unresolved.push("languages");

  return {
    intents,
    traits: [...traits],
    interests: [...interests],
    values: [...values],
    availability,
    languages: [...languages],
    unresolved,
  };
}

/**
 * What to ask next, or `null` when the intake is complete.
 *
 * The wording of the intent question is copied from
 * `OnboardingAgent.follow_up_question` and is neutral by construction: it
 * offers all three options in a fixed order and volunteers none of them. A
 * question that leans is inferring intent with extra steps.
 */
export function followUpFor(extraction: Extraction): string | null {
  if (extraction.unresolved.includes("intent")) {
    return (
      "Before we organise anything — what are you hoping to find here? " +
      "There is no wrong answer, and you can change it later."
    );
  }
  if (extraction.unresolved.includes("interests")) {
    return "What interests or hobbies do you enjoy?";
  }
  if (extraction.unresolved.includes("characteristics")) {
    return "Which characteristics best describe you?";
  }
  if (extraction.unresolved.includes("values")) {
    return "What matters most to you in a relationship or friendship?";
  }
  if (extraction.unresolved.includes("languages")) {
    return "Which languages are you comfortable speaking?";
  }
  return null;
}

// ---------------------------------------------------------------------------
// Rendering an extraction as chips
// ---------------------------------------------------------------------------

/** Time buckets, rendered for a person. Never a clock time, never a place. */
const AVAILABILITY_LABELS: Record<string, string> = {
  early_morning: "Early mornings",
  morning: "Mornings",
  midday: "Middays",
  afternoon: "Afternoons",
  evening: "Evenings",
  night: "Late nights",
};

function titleCase(term: string): string {
  return term.charAt(0).toUpperCase() + term.slice(1);
}

/**
 * The single place an extraction becomes chips.
 *
 * Shared by both adapters on purpose: `HttpAdapter` gets the real agent's
 * extraction over the wire and renders it through this same function, so the
 * demo and the backend cannot end up with two vocabularies for the same fact.
 *
 * Order is fixed — intent, traits, interests, values, availability, languages — so the
 * panel does not reshuffle between turns. Reshuffling chips is layout shift,
 * and this screen is on camera.
 */
export function chipsFor(extraction: Extraction): ProfileChip[] {
  const chips: ProfileChip[] = [];
  for (const intent of extraction.intents) {
    chips.push({ kind: "intent", label: intentLabel(intent) });
  }
  for (const trait of extraction.traits) {
    chips.push({ kind: "trait", label: titleCase(trait) });
  }
  for (const interest of extraction.interests) {
    chips.push({ kind: "interest", label: titleCase(interest) });
  }
  for (const value of extraction.values) {
    chips.push({ kind: "value", label: titleCase(value) });
  }
  for (const bucket of extraction.availability) {
    chips.push({
      kind: "availability",
      label: AVAILABILITY_LABELS[bucket] ?? titleCase(bucket),
    });
  }
  for (const language of extraction.languages) {
    chips.push({ kind: "language", label: titleCase(language) });
  }
  return chips;
}
