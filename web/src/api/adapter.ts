/**
 * The one interface every screen talks to — FRONTEND.md §4.
 *
 * Two implementations: `MockAdapter` (default, fully offline, deterministic)
 * and `HttpAdapter` (the FastAPI backend, `VITE_API=http`). No component ever
 * imports either directly; they call `getAdapter()`.
 *
 * That indirection is the reason the demo exists independently of the backend.
 * If the backend is late — and at the time of writing it does not exist at all
 * — every screen still runs, and switching over is one environment variable
 * rather than a refactor.
 */

import { HttpAdapter } from "./http";
import { MockAdapter } from "./mock";
import type {
  AgentEvent,
  ConsentOutcome,
  ContinuityBrief,
  DateMemory,
  DemoPersona,
  DatePlan,
  DatePreferences,
  EncounterCard,
  PlanLockIn,
  RejectionReason,
  LockIn,
  OnboardingTurn,
  RevealedPerson,
} from "./types";

/** A moment in the scripted call: what the ring and the waveform should show. */
export interface CallTick {
  /** Seconds elapsed, 0 -> 180. */
  elapsed: number;
  /** 0..1, drives the waveform. */
  amplitude: number;
  /** Who is speaking. Drives which side of the waveform is lit. */
  speaker: "local" | "remote" | "silence";
}

/** A Communication Agent suggestion, surfaced when the conversation stalls. */
export interface ConversationPrompt {
  /** Seconds into the call at which it appears. */
  atSecond: number;
  /** Stable id of the thing BOTH people raised. Present so fidelity can be
   *  checked by comparison rather than by reading two sentences and agreeing
   *  they are about the same subject. */
  topic: string;
  text: string;
  /** What each person actually said, LOOKED UP from the transcript in
   *  `callFixture.ts` rather than written beside the prompt. The agent may not
   *  invent a commonality, and a prompt that cannot fill both sides from the
   *  transcript cannot be constructed at all. */
  groundedIn: [string, string];
}

export interface Adapter {
  readonly name: "mock" | "http";

  /** Today's encounter, or null if the window has not opened. */
  getEncounter(): Promise<EncounterCard | null>;

  /** Accept or decline the notification. */
  respondToEncounter(encounterId: string, accept: boolean): Promise<void>;

  /**
   * The scripted audio for the call.
   *
   * Returned as data rather than streamed so the screen can drive its own
   * clock: a recording must not depend on adapter timing, and the ring has to
   * stay honest to `performance.now()`.
   */
  getCallScript(encounterId: string): Promise<{
    ticks: CallTick[];
    prompts: ConversationPrompt[];
  }>;

  /** The post-call decision. Returns what actually happened. */
  submitConsent(
    encounterId: string,
    yes: boolean,
  ): Promise<{ outcome: ConsentOutcome; person: RevealedPerson | null }>;

  /**
   * Up to three evenings for a pair who have already exchanged names.
   *
   * POST-REVEAL ONLY. The backend refuses with 409 before a mutual yes, and
   * the client guards the route as well — this is the one screen permitted to
   * name a kind of place, and it is permitted because two people who have
   * revealed are choosing where to go together.
   */
  getDatePlan(encounterId: string): Promise<DatePlan>;

  /**
   * Record the answer to Guardian's private check-in.
   *
   * Fire-and-record: the screen does not wait on it, because a safety exit must
   * never be blocked by a network call. Failures are swallowed HERE and nowhere
   * else — the person has already left the call, and an error toast about
   * logging is the last thing they need.
   */
  recordGuardianCheckIn(encounterId: string, allRight: boolean): Promise<void>;

  // --- Date Studio (§13.6) --------------------------------------------
  //
  // POST-REVEAL ONLY, and the server is the boundary. These calls return 409
  // when planning is not open — a React redirect is helpful UX and is never
  // what keeps a plan away from someone.

  /** Connections that can be planned with, and why any cannot. */
  getPlanLockIns(): Promise<PlanLockIn[]>;

  /** Saved constraints, plus the times the pair genuinely share. */
  getDatePreferences(lockInId: string): Promise<DatePreferences>;

  /** Three ranked plans. `remember` is opt-in and defaults to off. */
  generateDatePlans(
    lockInId: string,
    preferences: Partial<DatePreferences> & { remember?: boolean },
  ): Promise<DatePlan>;

  /** Structured feedback. Idempotent: repeating it must not double-learn. */
  sendDateFeedback(
    planId: string,
    action: "saved" | "rejected" | "completed",
    reasons?: RejectionReason[],
  ): Promise<void>;

  /** What Spark remembers about this viewer. */
  getDateMemory(lockInId?: string): Promise<DateMemory[]>;
  correctDateMemory(memoryId: string, value: string): Promise<void>;
  forgetDateMemory(memoryId: string): Promise<void>;

  getLockIns(): Promise<LockIn[]>;
  getBriefs(): Promise<ContinuityBrief[]>;

  /**
   * One turn of conversational intake (§5.1).
   *
   * Takes the CUMULATIVE transcript rather than the latest message, matching
   * `OnboardingAgent.extract(user_id, transcript)` on the Python side: someone
   * who names their interests in turn one and their availability in turn three
   * has said both, and a per-message extractor would keep asking about the
   * first.
   *
   * Returns the whole extraction every time, so the chip panel renders the
   * agent's current belief rather than a list the screen accumulated itself.
   * If the agent drops something, the panel drops it too.
   */
  extractProfile(transcript: string): Promise<OnboardingTurn>;

  /** The Director panel's feed. Subscribe returns an unsubscribe. */
  subscribeToAgentEvents(onEvent: (event: AgentEvent) => void): () => void;

  // --- demo controls (§8) --------------------------------------------
  //
  // ALL THREE RETURN PROMISES, including on `MockAdapter` where the work is
  // synchronous. Two of them used to return void while firing a request and
  // discarding it, so a take could begin before the reset had reached the
  // server — and the recording would show the previous take's state with no
  // indication that anything had gone wrong. An awaitable control is the
  // difference between "reset" and "reset, probably".

  /** Personas the demo can follow. Empty when the adapter has no world to
   *  choose from — the strip then hides the picker rather than showing one
   *  option that does nothing. */
  getDemoPersonas(): Promise<DemoPersona[]>;

  /** Follow this persona's day. Drops the current encounter. */
  actAsPersona(userId: string): Promise<void>;

  /** Another encounter, without wiping lock-ins or Date Studio memory. */
  newEncounter(): Promise<void>;

  /** Deterministic reset — same seed, same take. */
  reset(seed: number): Promise<void>;
  /** Force the next consent outcome, for filming each branch. */
  forceOutcome(outcome: ConsentOutcome | null): Promise<void>;
  /** Move the simulated clock forward, driving the Continuity Agent. */
  advanceDays(days: number): Promise<void>;
}

let cached: Adapter | null = null;

/**
 * MockAdapter unless `VITE_API=http` says otherwise.
 *
 * Defaulting to the mock is deliberate: `npm run dev` on a fresh clone, with no
 * backend and no keys, must produce a working app.
 */
export function getAdapter(): Adapter {
  if (cached) return cached;
  const mode = import.meta.env.VITE_API;
  cached = mode === "http" ? new HttpAdapter() : new MockAdapter();
  return cached;
}

/** Tests and the demo controls swap the adapter wholesale. */
export function setAdapter(adapter: Adapter | null): void {
  cached = adapter;
}
