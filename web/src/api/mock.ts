/**
 * MockAdapter — the whole product, scripted, with no backend.
 *
 * This is the default and it is what the submission video is filmed against.
 * Three properties matter more than realism:
 *
 *   DETERMINISM. Everything derives from a seed. The same seed produces the
 *   same encounter, the same amplitudes, the same agent timings — so a
 *   re-record matches the take before it, and §8's reset actually resets.
 *
 *   NO WALL CLOCK. Nothing here reads `Date.now()` for logic. Times are derived
 *   from a simulated "now" so advancing six weeks is a function call.
 *
 *   THE SAME WORLD AS THE EVALUATION. The handles, names and interests below
 *   are drawn from `spark/data/personas.json`, so what a judge sees on screen
 *   is the same synthetic cohort the three-arm evaluation ran over. A demo
 *   showing different data from the report invites the obvious question.
 *
 * INVARIANT NOTE: this file constructs `EncounterCard`, which has no field for
 * a name, a photo or a place — and it constructs `RevealedPerson` ONLY from
 * `submitConsent` when the outcome is mutual. There is no other path here that
 * produces an identity.
 */

import type { Adapter, CallTick, ConversationPrompt } from "./adapter";
import type {
  AgentEvent,
  ConsentOutcome,
  ContinuityBrief,
  DatePlan,
  EncounterCard,
  LockIn,
  OnboardingTurn,
  RevealedPerson,
} from "./types";
import {
  chipsFor,
  extractFromTranscript,
  followUpFor,
} from "./extract";
import { CONTINUITY_CITATION, SCRIPTED_PROMPTS } from "./callFixture";
import { overlapHintFor } from "./wire";

// ---------------------------------------------------------------------------
// Seeded randomness
// ---------------------------------------------------------------------------

/** mulberry32 — small, fast, and good enough for amplitudes and jitter. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// The world, mirrored from spark/data/personas.json
// ---------------------------------------------------------------------------

const CALL_SECONDS = 180;

/** Handles are assigned from a word list and never derived from a name. */
const PEER_HANDLE = "azure-heron";

/** Revealed only after a mutual yes. Synthetic — RFC 2606 reserved domain. */
const PEER_IDENTITY = {
  personId: "u001",
  displayName: "Belen Brackley",
  avatarSeed: "azure-heron",
} as const;

const SHARED_INTERESTS = ["coffee", "birdwatching"] as const;

/**
 * What each person said during the call lives in `callFixture.ts`, filed
 * under topic ids, and the prompts below LOOK UP their evidence there.
 *
 * It used to be two loose constants beside the prompts, and they drifted: a
 * prompt claiming "you both mentioned early mornings" cited a certification
 * exam and some birdwatching. Deriving the grounding removes the gap the
 * drift happened in.
 */

// ---------------------------------------------------------------------------
// The scripted call
// ---------------------------------------------------------------------------

/**
 * One tick per second of the call.
 *
 * Shaped rather than random: an opening where the remote speaks, a middle with
 * real back-and-forth, two deliberate stalls where the Communication Agent has
 * something to do, and a last thirty seconds that tails off. Pure noise would
 * read as a level meter, not a conversation.
 */
function buildCallScript(seed: number): {
  ticks: CallTick[];
  prompts: ConversationPrompt[];
} {
  const rand = mulberry32(seed + 1009);
  const ticks: CallTick[] = [];

  /** Deliberate silences — where a real conversation would stall. */
  const stalls = [
    [46, 54],
    [118, 126],
  ];

  for (let elapsed = 0; elapsed <= CALL_SECONDS; elapsed++) {
    const inStall = stalls.some(([a, b]) => elapsed >= a && elapsed <= b);

    let speaker: CallTick["speaker"];
    if (inStall) {
      speaker = "silence";
    } else if (elapsed < 8) {
      speaker = "remote"; // they say hello first
    } else {
      // Alternating turns of a few seconds each, not per-tick flicker.
      speaker = Math.floor(elapsed / 7) % 2 === 0 ? "local" : "remote";
    }

    let amplitude: number;
    if (speaker === "silence") {
      amplitude = 0.04 + rand() * 0.05; // room tone, never flat zero
    } else {
      // Syllable-rate wobble on top of a speech envelope.
      const envelope = 0.45 + 0.35 * Math.sin(elapsed / 2.7);
      amplitude = Math.min(1, Math.max(0.08, envelope + (rand() - 0.5) * 0.3));
      // The conversation winds down in the last half-minute.
      if (elapsed > 150) amplitude *= 1 - (elapsed - 150) / 60;
    }

    ticks.push({ elapsed, amplitude, speaker });
  }

  // Grounded by CONSTRUCTION. `SCRIPTED_PROMPTS` looks each prompt's evidence
  // up from the transcript and throws if the topic is not something both
  // people raised, so an invented commonality cannot reach this list.
  const prompts: ConversationPrompt[] = SCRIPTED_PROMPTS.map((prompt) => ({
    atSecond: prompt.atSecond,
    topic: prompt.topic,
    text: prompt.text,
    groundedIn: prompt.groundedIn,
  }));

  return { ticks, prompts };
}

// ---------------------------------------------------------------------------
// The agent event stream
// ---------------------------------------------------------------------------

interface ScriptedEvent extends Omit<AgentEvent, "ts"> {
  /** Seconds after the encounter window opens. */
  at: number;
}

/**
 * What the Director panel shows.
 *
 * The agent names, actions and rough costs mirror what the Python side actually
 * does — `match` shortlists then decides, `safety` screens every outbound
 * string, `delivery` owns the hard stop. A judge who opens `src/agents/` should
 * find the same vocabulary.
 */
const SCRIPT: ScriptedEvent[] = [
  { at: 0.0, agent: "match", action: "pooled overlap", detail: "7 paths crossed today; 4 eligible after intent, language and cooldown", durationMs: 38, status: "ok" },
  { at: 0.4, agent: "match", action: "shortlisted", detail: "5 candidates ranked on crossings, shared interests, availability, novelty, fairness", durationMs: 121, status: "ok" },
  { at: 1.2, agent: "match", action: "selected candidate", detail: "azure-heron — confidence 0.68. Estimates who is worth three minutes; does not predict attraction.", durationMs: 412, tokens: 1240, status: "ok" },
  { at: 1.8, agent: "safety", action: "screened notification", detail: "no identity, no place, no distance in outbound copy", durationMs: 88, status: "ok" },
  { at: 2.1, agent: "delivery", action: "notified both parties", detail: "anonymous card issued to each side", durationMs: 24, status: "ok" },
  { at: 12.0, agent: "delivery", action: "both accepted → connect", detail: "dual consent recorded; bridge opening", durationMs: 31, status: "ok" },
  { at: 12.4, agent: "delivery", action: "bridge opened", detail: "both legs anonymous; hard stop armed at 180s", durationMs: 96, status: "ok" },
  { at: 62.0, agent: "communication", action: "prompt (grounded)", detail: "cited what each person said; ungrounded suggestion would be withheld", durationMs: 380, tokens: 610, status: "ok" },
  { at: 96.0, agent: "safety", action: "screened prompt", detail: "passed", durationMs: 41, status: "ok" },
  { at: 134.0, agent: "communication", action: "prompt (grounded)", detail: "second stall detected", durationMs: 344, tokens: 580, status: "ok" },
  { at: 192.0, agent: "delivery", action: "hard stop at 180s", detail: "call ended by the time limit, not by either party", durationMs: 4, status: "ok" },
  { at: 193.0, agent: "delivery", action: "consent gate opened", detail: "asked privately of both; neither is told the other has answered", durationMs: 18, status: "ok" },
];

/**
 * How the trace ENDS depends on what actually happened.
 *
 * TWICE NOW THIS HAS BEEN WRONG, IN THE SAME DIRECTION.
 *
 * First it finished with "mutual yes → reveal" and a lock-in on every take, so
 * the panel narrated a reveal while the phone beside it showed a close-out.
 *
 * Then it read the FORCED PEER SETTING at subscribe time. That was still wrong
 * twice over: the app subscribes when it mounts and the operator picks the
 * outcome afterwards, so the choice was made before it could be known; and the
 * peer's setting is only half the answer — a viewer pressing No under a forced
 * "both yes" would still have been narrated a reveal.
 *
 * So this is no longer scheduled at all. It is emitted by `submitConsent`, from
 * the outcome that function actually returned. The trace cannot disagree with
 * the screen because it is now derived from the same value the screen is.
 */
function outcomeTail(outcome: ConsentOutcome): ScriptedEvent[] {
  if (outcome === "mutual") {
    return [
      { at: 205.0, agent: "delivery", action: "mutual yes → reveal", detail: "identities exchanged; this is the only path that produces a name", durationMs: 27, status: "ok" },
      { at: 205.6, agent: "continuity", action: "lock-in opened", detail: "note written to each party's own memory, scoped per user", durationMs: 210, tokens: 330, status: "ok" },
    ];
  }
  return [
    // Deliberately identical for `declined` and `no_response`. The operator
    // knows which they forced; the trace does not say, because a decline emits
    // no observable signal (INVARIANT 2) and the Director panel is observable.
    { at: 205.0, agent: "delivery", action: "no mutual yes → closed", detail: "the gate did not produce two yes answers; neither party is told what the other said", durationMs: 22, status: "ok" },
    { at: 205.4, agent: "safety", action: "screened close-out", detail: "identical copy on every non-connection; nothing inferable about the other side", durationMs: 37, status: "ok" },
  ];
}

// ---------------------------------------------------------------------------
// The adapter
// ---------------------------------------------------------------------------

export class MockAdapter implements Adapter {
  readonly name = "mock" as const;

  private seed = 42;
  /**
   * What the OTHER party does at the reveal gate. Never what the viewer does.
   *
   * `null` means "they say yes", the scripted happy path. This is a demo
   * control (FRONTEND.md §8) and it exists so each branch can be filmed — it
   * must never be able to change the outcome for a given pair of answers,
   * which is the thing invariant 3 is about.
   */
  private forced: ConsentOutcome | null = null;
  /**
   * Set ONLY by a mutual yes at the reveal gate.
   *
   * `getLockIns()` used to key off `accepted` — whether the NOTIFICATION had
   * been accepted — and so returned a lock-in carrying a name and an avatar
   * seed to anyone who had merely agreed to take the call. That is invariant 2
   * with the gate removed. A lock-in is a consequence of a reveal, and nothing
   * else in this file may set this flag.
   */
  private revealed = false;
  /** Simulated days since the lock-in opened. Drives the Continuity Agent. */
  private dayOffset = 0;
  private timers: ReturnType<typeof setTimeout>[] = [];
  /** Where trace events go, while something is listening. */
  private emit: ((event: AgentEvent) => void) | null = null;
  /** The simulated instant the current trace started, for event timestamps. */
  private traceStart = 0;

  /** A fixed simulated "now" so nothing depends on the wall clock. */
  private readonly epoch = new Date("2026-09-03T21:00:00+08:00").getTime();

  private get encounterId(): string {
    return `enc-2026-09-03-${this.seed.toString(16).padStart(6, "0")}`;
  }

  private simulatedNow(): Date {
    return new Date(this.epoch + this.dayOffset * 86_400_000);
  }

  async getEncounter(): Promise<EncounterCard> {
    return {
      encounterId: this.encounterId,
      state: "NOTIFIED",
      intent: "partner_long_term",
      handle: PEER_HANDLE,
      sharedInterests: [...SHARED_INTERESTS],
      // Words only. Derived from a coarse time bucket, never a place.
      overlapHint: overlapHintFor("afternoon"),
      windowClosesAt: new Date(this.epoch + 90 * 60_000).toISOString(),
      callSeconds: CALL_SECONDS,
    };
  }

  async respondToEncounter(_id: string, _accept: boolean): Promise<void> {
    // Nothing to record. Accepting the notification has no consequence a
    // later call reads: the lock-in is gated on the REVEAL (see `revealed`),
    // and storing the answer here once meant an accepted notification was
    // enough to produce a lock-in carrying somebody's name.
  }

  async getCallScript(): Promise<{
    ticks: CallTick[];
    prompts: ConversationPrompt[];
  }> {
    return buildCallScript(this.seed);
  }

  async submitConsent(
    _id: string,
    yes: boolean,
  ): Promise<{ outcome: ConsentOutcome; person: RevealedPerson | null }> {
    // THE VIEWER'S ANSWER IS CHECKED FIRST, AND ALONE.
    //
    // This used to read `this.forced ?? (yes ? "mutual" : "declined")`, which
    // let a demo control overrule a person. With "both yes" selected, a viewer
    // could press No and still be shown a name. The demo control is meant to
    // set what the OTHER party does; it had quietly become a switch that could
    // answer for the viewer too.
    //
    // A no is final and needs no second opinion, so it returns before the
    // forced outcome is even read. That ordering is the fix: there is no
    // expression below in which `forced` and `yes` are combined.
    if (!yes) {
      this.emitOutcome("declined");
      return { outcome: "declined", person: null };
    }

    // Only now does the other party get a say. `forced` is a demo control (§8)
    // so each branch can be filmed; unset means the scripted happy path.
    const peer: ConsentOutcome = this.forced ?? "mutual";

    // `declined` and `no_response` are returned distinctly so the operator can
    // film both. The CALLER must not branch on the difference — that is
    // invariant 3, and the consent test renders both and diffs the markup.
    if (peer !== "mutual") {
      this.emitOutcome(peer);
      return { outcome: peer, person: null };
    }

    // The ONLY assignment. A lock-in exists because BOTH people said yes.
    this.revealed = true;
    this.emitOutcome("mutual");
    return {
      outcome: "mutual",
      person: { ...PEER_IDENTITY, sharedInterests: [...SHARED_INTERESTS] },
    };
  }

  /**
   * Three scripted evenings, grounded in the same shared interests the reveal
   * screen shows.
   *
   * Gated on `revealed` for the same reason `getLockIns` is: a date plan names
   * places two people are going TOGETHER, which only makes sense — and is only
   * permitted — once they have both said yes.
   */
  async getDatePlan(_encounterId: string): Promise<DatePlan> {
    if (!this.revealed) {
      return {
        paths: [],
        note: "Date planning opens once you have both said yes.",
      };
    }
    return {
      note: "",
      paths: [
        {
          pathId: "path-birds",
          headline:
            "A morning walk with binoculars, then a wet market breakfast",
          stops: [
            { venueId: "v-birds", activity: "a morning walk with binoculars", category: "activity", isCommercialPartner: false },
            { venueId: "f-market", activity: "a wet market breakfast", category: "food", isCommercialPartner: false },
          ],
          groundedIn: ["birdwatching"],
          rationale:
            "You have both mentioned birdwatching, and you are both usually free in the early morning.",
          proposedBucket: "early_morning",
        },
        {
          pathId: "path-coffee",
          headline: "Three cafes in an afternoon, ranked, then a tea house, the slow kind",
          stops: [
            { venueId: "v-cafe", activity: "three cafes in an afternoon, ranked", category: "activity", isCommercialPartner: false },
            { venueId: "d-tea", activity: "a tea house, the slow kind", category: "drink", isCommercialPartner: false },
          ],
          groundedIn: ["coffee"],
          rationale:
            "You have both mentioned coffee, and you are both usually free in the afternoon.",
          proposedBucket: "afternoon",
        },
        {
          pathId: "path-bakery",
          headline: "A bakery that does one thing properly",
          stops: [
            // A commercial partner, and labelled as one. §13.6: partners may
            // only appear where they already rank, and are always disclosed.
            { venueId: "f-bakery", activity: "a bakery that does one thing properly", category: "food", isCommercialPartner: true },
          ],
          groundedIn: ["coffee"],
          rationale:
            "You have both mentioned coffee, and you are both usually free in the early morning.",
          proposedBucket: "early_morning",
        },
      ],
    };
  }

  async recordGuardianCheckIn(
    _encounterId: string,
    _allRight: boolean,
  ): Promise<void> {
    // Nothing to record offline. The consequence a person can SEE — the
    // encounter closing without the reveal gate opening — is in `Call.tsx`
    // and does not depend on this.
  }

  async getLockIns(): Promise<LockIn[]> {
    // Gated on the REVEAL, not on the acceptance. See `revealed`.
    if (!this.revealed) return [];
    const opened = new Date(this.epoch);
    const lastContact =
      this.dayOffset === 0
        ? opened
        : new Date(this.epoch + Math.min(this.dayOffset, 4) * 86_400_000);

    return [
      {
        lockInId: "lock-78f62d9d60cf",
        person: { ...PEER_IDENTITY, sharedInterests: [...SHARED_INTERESTS] },
        openedAt: opened.toISOString(),
        lastContactAt: lastContact.toISOString(),
        // Goes quiet after ten days without contact — the same threshold the
        // Python Continuity Agent uses.
        state: this.dayOffset >= 10 ? "quiet" : "active",
      },
    ];
  }

  async getBriefs(): Promise<ContinuityBrief[]> {
    const lockIns = await this.getLockIns();
    if (lockIns.length === 0) return [];

    // Week 1 recalls; week 5 proposes. The difference is the whole "plans, acts
    // and adapts over time" claim, and it has to be visible on screen.
    const week = Math.floor(this.dayOffset / 7) + 1;
    return [
      week >= 5
        ? {
            lockInId: "lock-78f62d9d60cf",
            line: `You have spoken four times. She mentioned ${CONTINUITY_CITATION}.`,
            suggestedAction: "Suggest meeting",
            sourceEncounterId: this.encounterId,
          }
        : {
            lockInId: "lock-78f62d9d60cf",
            line: `She mentioned ${CONTINUITY_CITATION}.`,
            suggestedAction: "Ask how it went",
            sourceEncounterId: this.encounterId,
          },
    ];
  }

  subscribeToAgentEvents(onEvent: (event: AgentEvent) => void): () => void {
    const start = this.simulatedNow().getTime();
    // Replayed at 1:6 so the events land across a filmable window rather than
    // over three and a half minutes of dead air.
    const RATE = 6;

    // Only the part of the run that is already decided. Everything up to and
    // including "consent gate opened" happens regardless of how the gate is
    // answered, so it can be scheduled. The ending cannot, and is not.
    this.emit = onEvent;
    this.traceStart = start;

    for (const scripted of SCRIPT) {
      const timer = setTimeout(
        () => {
          const { at, ...rest } = scripted;
          onEvent({ ...rest, ts: new Date(start + at * 1000).toISOString() });
        },
        (scripted.at * 1000) / RATE,
      );
      this.timers.push(timer);
    }

    return () => {
      this.timers.forEach(clearTimeout);
      this.timers = [];
      // Only clear the sink if it is still ours. The app resubscribes on reset,
      // and a late unsubscribe from the previous subscription must not silence
      // the new one.
      if (this.emit === onEvent) this.emit = null;
    };
  }

  /**
   * The end of the trace, emitted from the outcome that actually happened.
   *
   * Called by `submitConsent` and by nothing else, so there is no path that
   * produces a reveal in the panel without producing one on the screen.
   */
  private emitOutcome(outcome: ConsentOutcome): void {
    const emit = this.emit;
    if (!emit) return;
    for (const scripted of outcomeTail(outcome)) {
      const { at, ...rest } = scripted;
      emit({ ...rest, ts: new Date(this.traceStart + at * 1000).toISOString() });
    }
  }

  // --- demo controls -------------------------------------------------

  // Async to match the interface, though the work here is synchronous. The
  // caller must not have to know which adapter it is holding.
  async reset(seed: number): Promise<void> {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    // Drop the sink too. The app resubscribes when `traceEpoch` changes, and a
    // take that is being thrown away must not emit into the next one's panel.
    this.emit = null;
    this.seed = seed;
    this.forced = null;
    this.dayOffset = 0;
    this.revealed = false;
  }

  async forceOutcome(outcome: ConsentOutcome | null): Promise<void> {
    this.forced = outcome;
  }

  async advanceDays(days: number): Promise<void> {
    this.dayOffset += days;
  }
  // --- onboarding (§5.1) ---------------------------------------------

  /**
   * The Onboarding Agent, offline.
   *
   * This runs the deterministic path in `extract.ts`, which mirrors the same
   * path in `spark/src/agents/onboarding.py`. `HttpAdapter` calls the real
   * agent instead, and the two agree about the rule that matters: intent is
   * only set when the transcript NAMES it.
   */
  async extractProfile(transcript: string): Promise<OnboardingTurn> {
    const extraction = extractFromTranscript(transcript);
    return {
      chips: chipsFor(extraction),
      followUp: followUpFor(extraction),
      unresolved: extraction.unresolved,
    };
  }

}
