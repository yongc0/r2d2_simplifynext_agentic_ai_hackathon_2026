/**
 * The client contract — FRONTEND.md §4, reconciled with `spark/src/schemas/`.
 *
 * Where the two disagreed, `wire.ts` holds the decision and the reasoning. This
 * file is the shape the components actually consume.
 *
 * The comments marked INVARIANT are not documentation. They are the reason a
 * field is absent, and a field added against one of them undoes the product's
 * central safety claim.
 */

/**
 * What the CLIENT is showing. Not the backend's `EncounterState` — see note 2
 * in `wire.ts` for why these are deliberately two types.
 */
export type ClientState =
  | "IDLE"
  | "WINDOW_OPEN"
  | "NOTIFIED"
  | "PENDING_ACCEPT"
  | "CONNECTED"
  | "CALL_ENDED"
  | "PENDING_CONSENT"
  | "REVEALED"
  | "CLOSED"
  | "ABANDONED";

/** Values match `spark/src/schemas/core.py::Intent` exactly. */
export type Intent = "partner_long_term" | "partner_short_term" | "friends";

/** Matches `LockInState` on the Python side. */
export type LockInStatus = "active" | "quiet" | "released";

/**
 * What a user is shown when today's encounter is offered.
 *
 * INVARIANT 2 (no identity pre-reveal): there is no `name`, `displayName`,
 * `age`, `photo`, `avatar`, or `initial` field, and there must not be one. The
 * pseudonymous `handle` is not an identity — see note 3 in `wire.ts`.
 *
 * INVARIANT 1 (no location): there is no `distance`, `place`, `cell`, `lat`,
 * `lng`, or `coordinates` field. `overlapHint` is a rendered phrase — "Your
 * paths crossed this afternoon" — produced from a coarse time bucket by
 * `overlapHintFor`. It cannot express a place because nothing upstream of it
 * knows one.
 */
export interface EncounterCard {
  encounterId: string;
  state: ClientState;
  intent: Intent;
  /** Pseudonymous, from a fixed word list. Never derived from a name. */
  handle: string;
  /** Interests BOTH people listed. Never the other person's full list, which
   *  would be a fingerprint. */
  sharedInterests: string[];
  /** Words only. Never a place, never a distance. */
  overlapHint: string;
  /** ISO. When the offer lapses. */
  windowClosesAt: string;
  /** Always 180. Present so the UI states the limit rather than assuming it. */
  callSeconds: number;
}

/**
 * The only object in the client that carries an identity.
 *
 * Constructed exclusively from a mutual-yes reveal. `avatarSeed` drives a
 * generated illustration (INVARIANT 7) — it is never a photograph, and there is
 * no field here that could hold a URL to one.
 */
export interface RevealedPerson {
  personId: string;
  displayName: string;
  avatarSeed: string;
  sharedInterests: string[];
}

export interface LockIn {
  lockInId: string;
  person: RevealedPerson;
  openedAt: string;
  lastContactAt: string | null;
  state: LockInStatus;
}

/**
 * What the Continuity Agent surfaces before the next contact.
 *
 * `line` must quote something the pair actually discussed. A brief with nothing
 * to cite is not sent — that is the difference between continuity and a
 * reminder, and the backend enforces it on `ContinuityAction.reference`.
 */
export interface ContinuityBrief {
  lockInId: string;
  line: string;
  suggestedAction: string;
  sourceEncounterId: string;
}

/** The agents, exactly as `spark/src/agents/` names them, plus safety. */
export type AgentName =
  | "onboarding"
  | "match"
  | "delivery"
  | "continuity"
  | "communication"
  | "date"
  | "guardian"
  | "safety";

/** One row in the Director panel (§6). */
export interface AgentEvent {
  ts: string;
  agent: AgentName;
  action: string;
  detail: string;
  durationMs: number;
  tokens?: number;
  status: "ok" | "retry" | "error";
}

/** The three outcomes of the post-call gate.
 *
 *  INVARIANT 3: `declined` and `no_response` must produce an IDENTICAL screen,
 *  with identical copy and identical timing. They are distinguished here only
 *  so the demo controls can film each branch; nothing downstream of the store
 *  may branch on the difference. `web/src/__tests__/invariants.test.tsx`
 *  asserts that. */
export type ConsentOutcome = "mutual" | "declined" | "no_response";

// ---------------------------------------------------------------------------
// Onboarding (§5.1)
// ---------------------------------------------------------------------------

/**
 * The kinds of thing intake can capture.
 *
 * INVARIANT 5 (no height, appearance or photo-based filtering): this union is
 * the complete list, and there is no member for a physical attribute. A chip
 * for one cannot be constructed, so no amount of editing the onboarding screen
 * can put one on the panel.
 */
export type ChipKind =
  | "intent"
  | "interest"
  | "value"
  | "availability"
  | "language";

/** One extracted fact, rendered as a chip that animates in as it is captured. */
export interface ProfileChip {
  kind: ChipKind;
  /** Already rendered for a person — British spelling, per CLAUDE.md. */
  label: string;
}

/**
 * What the Onboarding Agent returns for a turn of intake.
 *
 * `followUp` comes from the agent rather than the screen. That is deliberate:
 * the neutral wording of the intent question is part of the rule that intent is
 * never inferred, and a screen that composed its own question could lean
 * without anyone noticing.
 */
export interface OnboardingTurn {
  /** The cumulative extraction, not this turn's delta. */
  chips: ProfileChip[];
  /** The next question, or null when the intake is complete. */
  followUp: string | null;
  /** Field names still to be resolved. Mirrors `OnboardingExtraction`. */
  unresolved: string[];
}

// ---------------------------------------------------------------------------
// Date planning (§13.6)
// ---------------------------------------------------------------------------

/**
 * One place in a suggested evening.
 *
 * INVARIANT 1 (no location): there is no `address`, `distance`, `lat`, `lng`,
 * `cell` or `mapUrl` field, and there must not be one. A stop is a KIND of
 * place — "a hawker centre, one dish each and swap" — never a named business
 * at an address.
 *
 * This is the one feature in the product allowed to point somewhere, and it is
 * allowed because it runs only AFTER a mutual reveal: two people choosing where
 * to meet are picking a destination together, which is not a disclosure of
 * where either of them was. The backend never gives the venue search a
 * location, so "near where you both were" cannot be built.
 */
export interface DateStop {
  venueId: string;
  activity: string;
  category: "activity" | "food" | "drink";
  /** Required, not optional, so a partner venue cannot render without its
   *  label. Commercial partners are disclosed beside the venue, never in
   *  fine print. */
  isCommercialPartner: boolean;
}

/** One suggested evening: a thing to do, and somewhere to eat or sit. */
export interface DatePath {
  pathId: string;
  /** Composed from the stops, never written by a model. */
  headline: string;
  stops: DateStop[];
  /** Interests BOTH people listed. Never empty — the agent will not build a
   *  path it cannot ground, for the same reason the Communication Agent will
   *  not invent a shared interest. */
  groundedIn: string[];
  rationale: string;
  proposedBucket: string;
}

export interface DatePlan {
  paths: DatePath[];
  /** Why the plan is short or empty, so it reads as a fact about the pair
   *  rather than as a failure. */
  note: string;
}
