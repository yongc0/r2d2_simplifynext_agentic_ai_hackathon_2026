/**
 * MockAdapter — milestone 2's acceptance test.
 *
 * The properties that matter are determinism (so takes are repeatable) and the
 * invariants (so the scripted data cannot be the thing that leaks).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentEvent, ConsentOutcome } from "../api/types";

import {
  CONTINUITY_CITATION,
  saidBy,
  sharedGrounding,
} from "../api/callFixture";
import { MockAdapter } from "../api/mock";
import { scanForIdentityFields, scanForLocation } from "./scanners";

let adapter: MockAdapter;

beforeEach(() => {
  adapter = new MockAdapter();
  adapter.reset(42);
});

describe("determinism", () => {
  it("the same seed produces the same call, byte for byte", async () => {
    const a = new MockAdapter();
    a.reset(42);
    const b = new MockAdapter();
    b.reset(42);
    expect(await a.getCallScript()).toEqual(await b.getCallScript());
  });

  it("a different seed produces a different call", async () => {
    const a = new MockAdapter();
    a.reset(42);
    const b = new MockAdapter();
    b.reset(7);
    expect(await a.getCallScript()).not.toEqual(await b.getCallScript());
  });

  it("reset returns the adapter to its opening state", async () => {
    await adapter.respondToEncounter("e", true);
    await adapter.advanceDays(30);
    adapter.forceOutcome("declined");

    adapter.reset(42);

    expect(await adapter.getLockIns()).toHaveLength(0);
    const { outcome } = await adapter.submitConsent("e", true);
    expect(outcome).toBe("mutual"); // the forced outcome was cleared
  });
});

describe("the scripted call", () => {
  it("runs exactly 180 seconds", async () => {
    const { ticks } = await adapter.getCallScript();
    expect(ticks[0].elapsed).toBe(0);
    expect(ticks.at(-1)!.elapsed).toBe(180);
  });

  it("has amplitude in range throughout, and never a flat line", async () => {
    const { ticks } = await adapter.getCallScript();
    for (const t of ticks) {
      expect(t.amplitude).toBeGreaterThan(0);
      expect(t.amplitude).toBeLessThanOrEqual(1);
    }
    // Room tone during a silence, not digital zero — a waveform that flatlines
    // reads as a dropped call rather than a pause.
    const silences = ticks.filter((t) => t.speaker === "silence");
    expect(silences.length).toBeGreaterThan(0);
    for (const t of silences) expect(t.amplitude).toBeGreaterThan(0.01);
  });

  it("both people speak", async () => {
    const { ticks } = await adapter.getCallScript();
    const speakers = new Set(ticks.map((t) => t.speaker));
    expect(speakers).toContain("local");
    expect(speakers).toContain("remote");
  });

  it("every prompt is grounded in something BOTH people said", async () => {
    // The Communication Agent may not invent a shared interest, and this test
    // used to check only that `groundedIn` held two non-empty strings — which
    // a prompt reading "you both mentioned early mornings", evidenced by a
    // certification exam and some birdwatching, passed without difficulty.
    //
    // So the check is now on TOPIC IDENTITY. Whether two English sentences are
    // about the same subject is not something a unit test can decide; whether
    // both speakers filed a quote under the same topic id is.
    const { prompts } = await adapter.getCallScript();
    expect(prompts.length).toBeGreaterThan(0);

    for (const p of prompts) {
      const local = saidBy("local", p.topic);
      const remote = saidBy("remote", p.topic);

      expect(local, `no local quote for topic "${p.topic}"`).not.toBeNull();
      expect(remote, `no remote quote for topic "${p.topic}"`).not.toBeNull();

      // And the evidence attached is exactly those two quotes, not some other
      // pair that happens to be two non-empty strings.
      expect(p.groundedIn).toEqual([local, remote]);
    }
  });

  it("refuses to ground a prompt in something only one person said", () => {
    // The certification exam is single-sided: the remote speaker raised it and
    // the local one never did. A prompt claiming it as a commonality is
    // precisely the hallucination the rule forbids, and it cannot be built.
    expect(() => sharedGrounding("certification-exam")).toThrow(/never raised it/);
    expect(() => sharedGrounding("something-nobody-said")).toThrow();
  });

  it("the continuity brief quotes the person it says it is quoting", () => {
    // It cites "she mentioned ...", so the quote must be the REMOTE speaker's.
    // It previously came from a constant named SAID_BY_LOCAL, which attributed
    // the user's own words to the person they had just met.
    expect(CONTINUITY_CITATION).toBe(saidBy("remote", "certification-exam"));
    expect(CONTINUITY_CITATION).not.toBe(saidBy("local", "early-mornings"));
  });

  it("prompts appear during a stall, not over someone talking", async () => {
    const { ticks, prompts } = await adapter.getCallScript();
    for (const p of prompts) {
      const tick = ticks.find((t) => t.elapsed === p.atSecond)!;
      expect(tick.speaker, `prompt at ${p.atSecond}s`).toBe("silence");
    }
  });
});

describe("invariants in the scripted data", () => {
  it("the encounter card carries no identity and no location", async () => {
    const card = await adapter.getEncounter();
    expect(scanForIdentityFields(card)).toHaveLength(0);
    expect(scanForLocation(JSON.stringify(card))).toHaveLength(0);
  });

  it("nothing in the call script leaks an identity or a place", async () => {
    const script = await adapter.getCallScript();
    expect(scanForLocation(JSON.stringify(script))).toHaveLength(0);
    expect(scanForIdentityFields(script)).toHaveLength(0);
  });

  it("no identity is produced on any non-mutual outcome", async () => {
    for (const forced of ["declined", "no_response"] as const) {
      adapter.reset(42);
      adapter.forceOutcome(forced);
      const { outcome, person } = await adapter.submitConsent("e", true);
      expect(outcome).toBe(forced);
      expect(person).toBeNull();
    }
  });

  it("an identity appears only on a mutual yes", async () => {
    const { outcome, person } = await adapter.submitConsent("e", true);
    expect(outcome).toBe("mutual");
    expect(person?.displayName).toBeTruthy();
    // Generated illustration, never a photograph (invariant 7). There is no
    // field here that could hold a URL to one.
    expect(person).not.toHaveProperty("photoUrl");
    expect(person).not.toHaveProperty("avatarUrl");
    expect(person!.avatarSeed).toBeTruthy();
  });

  it("agent events carry no identity and no location", async () => {
    const seen: unknown[] = [];
    const stop = adapter.subscribeToAgentEvents((e) => seen.push(e));
    await new Promise((r) => setTimeout(r, 400));
    stop();
    expect(seen.length).toBeGreaterThan(0);
    expect(scanForLocation(JSON.stringify(seen))).toHaveLength(0);
  });
});

describe("continuity over weeks", () => {
  /** A lock-in exists only after a MUTUAL YES. Accepting the notification is
   *  not enough, and these tests go the whole way rather than short-cutting to
   *  the state they want — that short cut is what let `getLockIns()` hand back
   *  a name to someone who had only agreed to take the call. */
  async function connect() {
    await adapter.respondToEncounter("e", true);
    await adapter.submitConsent("e", true);
  }

  it("week 5 says something different from week 1", async () => {
    await connect();

    const early = await adapter.getBriefs();
    await adapter.advanceDays(30);
    const late = await adapter.getBriefs();

    expect(early[0].line).not.toEqual(late[0].line);
    expect(early[0].suggestedAction).toBe("Ask how it went");
    expect(late[0].suggestedAction).toBe("Suggest meeting");
  });

  it("a brief always cites something the pair actually discussed", async () => {
    for (const days of [0, 7, 21, 35]) {
      await adapter.reset(42);
      await connect();
      await adapter.advanceDays(days);
      const [brief] = await adapter.getBriefs();
      // The note the Python side would have stored. A brief with nothing to
      // cite is a reminder, not continuity, and is not sent.
      expect(brief.line).toContain("certification exam");
    }
  });

  it("a lock-in goes quiet after ten days, matching the backend threshold", async () => {
    await connect();
    expect((await adapter.getLockIns())[0].state).toBe("active");
    await adapter.advanceDays(12);
    expect((await adapter.getLockIns())[0].state).toBe("quiet");
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 2 — a lock-in is a consequence of a reveal
// ---------------------------------------------------------------------------

describe("no identity-bearing object before a mutual yes", () => {
  it("has no lock-in merely because the notification was accepted", async () => {
    // `getLockIns()` used to key off acceptance, so agreeing to TAKE the call
    // produced a lock-in carrying a name and an avatar seed — invariant 2 with
    // the gate removed.
    await adapter.respondToEncounter("e", true);
    expect(await adapter.getLockIns()).toEqual([]);
    expect(await adapter.getBriefs()).toEqual([]);
  });

  it("has no lock-in after a decline", async () => {
    await adapter.respondToEncounter("e", true);
    await adapter.submitConsent("e", false);
    expect(await adapter.getLockIns()).toEqual([]);
  });

  it("has one only after both said yes", async () => {
    await adapter.respondToEncounter("e", true);
    await adapter.submitConsent("e", true);
    const lockIns = await adapter.getLockIns();
    expect(lockIns).toHaveLength(1);
    expect(lockIns[0].person.displayName).toBeTruthy();
  });

  it("forgets the reveal on reset, so a retake starts anonymous", async () => {
    await adapter.respondToEncounter("e", true);
    await adapter.submitConsent("e", true);
    await adapter.reset(42);
    expect(await adapter.getLockIns()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// The demo control is the PEER's answer, never the viewer's
// ---------------------------------------------------------------------------

describe("a local no is final, whatever the demo control says", () => {
  // `submitConsent` used to read `forced ?? (yes ? "mutual" : "declined")`, so
  // with "both yes" selected a viewer could press No and still be shown a name.
  // A demo control that can answer FOR a person is not a demo control.

  it("never reveals when the viewer says no, even with peer yes forced", async () => {
    await adapter.forceOutcome("mutual");
    const result = await adapter.submitConsent("e", false);

    expect(result.outcome).not.toBe("mutual");
    expect(result.person).toBeNull();
  });

  it("reveals when the viewer says yes and the peer is forced to yes", async () => {
    await adapter.forceOutcome("mutual");
    const result = await adapter.submitConsent("e", true);

    expect(result.outcome).toBe("mutual");
    expect(result.person?.displayName).toBeTruthy();
  });

  it.each(["declined", "no_response"] as const)(
    "does not reveal when the viewer says yes but the peer is %s",
    async (peer) => {
      await adapter.forceOutcome(peer);
      const result = await adapter.submitConsent("e", true);

      expect(result.outcome).toBe(peer);
      expect(result.person).toBeNull();
    },
  );

  it.each([
    ["mutual", false],
    ["declined", true],
    ["declined", false],
    ["no_response", true],
    ["no_response", false],
    [null, false],
  ] as const)(
    "opens no lock-in for forced=%s / local=%s",
    async (peer, local) => {
      // A lock-in carries a name. Every combination that is not "both said yes"
      // must leave the list empty — checked exhaustively rather than for the
      // one case that happened to be reported.
      await adapter.forceOutcome(peer);
      const result = await adapter.submitConsent("e", local);

      expect(result.person).toBeNull();
      expect(await adapter.getLockIns()).toEqual([]);
      expect(await adapter.getBriefs()).toEqual([]);
    },
  );

  it("opens a lock-in only for the one combination that earns it", async () => {
    await adapter.forceOutcome("mutual");
    await adapter.submitConsent("e", true);
    expect(await adapter.getLockIns()).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// The Director trace must agree with the screen
// ---------------------------------------------------------------------------

describe("the trace ending is decided by what actually happened", () => {
  // THE ORDER THESE RUN IN IS THE POINT.
  //
  // The app subscribes when it mounts; the operator picks the forced outcome
  // afterwards, and the viewer answers after that. An earlier version chose the
  // ending at subscribe time from the peer setting alone, which was wrong twice:
  // the setting had not been made yet, and the peer is only half the answer.
  // A viewer pressing No under a forced "both yes" got a close-out on the phone
  // and "mutual yes → reveal" in the panel.
  //
  // So these tests subscribe FIRST, force the peer outcome SECOND, and answer
  // THIRD — the sequence a person actually performs.

  interface Session {
    events: AgentEvent[];
    stop: () => void;
  }

  /** Subscribe and play out everything that happens before the gate is
   *  answered. Fake timers, because the head replays over ~34s. */
  function subscribeAndAdvance(): Session {
    vi.useFakeTimers();
    try {
      const events: AgentEvent[] = [];
      const stop = adapter.subscribeToAgentEvents((e) => events.push(e));
      vi.advanceTimersByTime(60_000);
      return { events, stop };
    } finally {
      vi.useRealTimers();
    }
  }

  const actionsOf = (s: Session) => s.events.map((e) => e.action);

  it("narrates nothing about the ending until the gate is answered", () => {
    const session = subscribeAndAdvance();
    const actions = actionsOf(session);

    // The head has fully played out...
    expect(actions).toContain("consent gate opened");
    // ...and the ending is simply not there yet, because it has not happened.
    expect(actions).not.toContain("mutual yes → reveal");
    expect(actions).not.toContain("no mutual yes → closed");
    session.stop();
  });

  it("narrates a reveal only when both actually said yes", async () => {
    const session = subscribeAndAdvance();
    await adapter.forceOutcome("mutual");           // operator, after mounting
    await adapter.submitConsent("e", true);          // viewer, after that

    const actions = actionsOf(session);
    expect(actions).toContain("mutual yes → reveal");
    expect(actions).toContain("lock-in opened");
    session.stop();
  });

  it("narrates a close-out when the viewer says no under a forced peer yes", async () => {
    // The exact contradiction that was reported: the phone closes out, and the
    // panel used to announce a reveal beside it.
    const session = subscribeAndAdvance();
    await adapter.forceOutcome("mutual");
    const result = await adapter.submitConsent("e", false);

    expect(result.outcome).not.toBe("mutual");
    const actions = actionsOf(session);
    expect(actions).toContain("no mutual yes → closed");
    expect(actions).not.toContain("mutual yes → reveal");
    expect(actions).not.toContain("lock-in opened");
    session.stop();
  });

  it.each([null, "mutual", "declined", "no_response"] as const)(
    "never narrates a reveal after a local no, with peer=%s",
    async (peer) => {
      const session = subscribeAndAdvance();
      await adapter.forceOutcome(peer);
      await adapter.submitConsent("e", false);

      const actions = actionsOf(session);
      expect(actions).not.toContain("mutual yes → reveal");
      expect(actions).not.toContain("lock-in opened");
      expect(actions).toContain("no mutual yes → closed");
      session.stop();
    },
  );

  it.each(["declined", "no_response"] as const)(
    "narrates a close-out when the viewer says yes but the peer is %s",
    async (peer) => {
      const session = subscribeAndAdvance();
      await adapter.forceOutcome(peer);
      await adapter.submitConsent("e", true);

      const actions = actionsOf(session);
      expect(actions).toContain("no mutual yes → closed");
      expect(actions).not.toContain("mutual yes → reveal");
      session.stop();
    },
  );

  it("says exactly the same thing for a decline and a no-response", async () => {
    // INVARIANT 2 reaches the Director panel: it is observable, so it must not
    // distinguish "they said no" from "they never answered".
    const fingerprint = async (peer: ConsentOutcome) => {
      await adapter.reset(42);
      const session = subscribeAndAdvance();
      await adapter.forceOutcome(peer);
      await adapter.submitConsent("e", true);
      const rows = session.events
        .slice(-2)
        .map((e) => `${e.agent}:${e.action}:${e.detail}:${e.status}`);
      session.stop();
      return rows;
    };

    expect(await fingerprint("declined")).toEqual(
      await fingerprint("no_response"),
    );
  });

  it("emits nothing once the panel has stopped listening", async () => {
    const session = subscribeAndAdvance();
    const before = session.events.length;
    session.stop();

    await adapter.submitConsent("e", true);
    expect(session.events.length).toBe(before);
  });
});
