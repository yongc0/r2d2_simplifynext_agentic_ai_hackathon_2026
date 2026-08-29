/**
 * HttpAdapter — the same interface, against the real backend.
 *
 * Enabled with `VITE_API=http`. Everything goes through `/api`, which Vite
 * proxies to the FastAPI process, so ONE origin (and later one tunnel) serves
 * both halves.
 *
 * The point of the adapter boundary is that this file is the whole diff. No
 * screen imports it, no screen knows which implementation it is talking to, and
 * nothing below `getAdapter()` changed when this landed.
 *
 * INVARIANT NOTE: the endpoints this calls return no identity before a mutual
 * yes and no location at all — `spark/src/api/schemas.py` has no field for
 * either on the pre-reveal models. This adapter adds nothing to what it is
 * given, so it cannot introduce one.
 */

import type { Adapter, CallTick, ConversationPrompt } from "./adapter";
import { chipsFor, type Extraction } from "./extract";

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

const BASE = "/api";

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    detail: string,
  ) {
    // Actionable, per CLAUDE.md: what failed, where, and what it means —
    // never "request failed".
    super(`${path} returned ${status}: ${detail}`);
  }
}

async function call<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (cause) {
    throw new HttpError(
      0,
      path,
      "the backend is unreachable. Start it with `cd spark && uv run -m src.api`, " +
        "or unset VITE_API to use MockAdapter.",
    );
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new HttpError(response.status, path, detail.slice(0, 300));
  }
  return (await response.json()) as T;
}

export class HttpAdapter implements Adapter {
  readonly name = "http" as const;

  /** The encounter this session is working on, so later calls can address it. */
  private encounterId: string | null = null;

  async getEncounter(): Promise<EncounterCard | null> {
    try {
      const card = await call<EncounterCard>("/encounters", { method: "POST" });
      this.encounterId = card.encounterId;
      return card;
    } catch (error) {
      // 409 is a QUIET DAY, not a failure: nobody eligible crossed this
      // person's path. The client shows the empty home screen, which is the
      // product's argument rather than an error state.
      if (error instanceof HttpError && error.status === 409) return null;
      throw error;
    }
  }

  async respondToEncounter(encounterId: string, accept: boolean): Promise<void> {
    await call(`/encounters/${encounterId}/respond`, {
      method: "POST",
      body: JSON.stringify({ accept }),
    });
  }

  async getCallScript(encounterId: string): Promise<{
    ticks: CallTick[];
    prompts: ConversationPrompt[];
  }> {
    const id = encounterId || this.encounterId;
    if (!id) throw new Error("getCallScript called before an encounter was opened");
    return call<{ ticks: CallTick[]; prompts: ConversationPrompt[] }>(
      `/encounters/${id}/call-script`,
    );
  }

  async submitConsent(
    encounterId: string,
    yes: boolean,
  ): Promise<{ outcome: ConsentOutcome; person: RevealedPerson | null }> {
    const id = encounterId || this.encounterId;
    if (!id) throw new Error("submitConsent called before an encounter was opened");
    return call<{ outcome: ConsentOutcome; person: RevealedPerson | null }>(
      `/encounters/${id}/consent`,
      { method: "POST", body: JSON.stringify({ yes }) },
    );
  }

  async getDatePlan(encounterId: string): Promise<DatePlan> {
    const id = encounterId || this.encounterId;
    if (!id) throw new Error("getDatePlan called before an encounter was opened");
    try {
      return await call<DatePlan>(`/encounters/${id}/dates`);
    } catch (error) {
      // 409 is "not yet", not a failure: the pair have not both said yes. The
      // screen shows the reason rather than an error state.
      if (error instanceof HttpError && error.status === 409) {
        return {
          paths: [],
          note: "Date planning opens once you have both said yes.",
        };
      }
      throw error;
    }
  }

  async recordGuardianCheckIn(
    encounterId: string,
    allRight: boolean,
  ): Promise<void> {
    const id = encounterId || this.encounterId;
    if (!id) return;
    await call(`/encounters/${id}/guardian/check-in`, {
      method: "POST",
      body: JSON.stringify({ allRight }),
    });
  }

  async getLockIns(): Promise<LockIn[]> {
    return call<LockIn[]>("/lockins");
  }

  async getBriefs(): Promise<ContinuityBrief[]> {
    return call<ContinuityBrief[]>("/briefs");
  }
  /**
   * One turn of intake, run by the REAL Onboarding Agent.
   *
   * The server returns the extraction and the follow-up question; the client
   * turns it into chips with the same `chipsFor` the mock uses, so the two
   * adapters cannot end up with two vocabularies for the same fact.
   *
   * The follow-up is the SERVER'S wording, not ours. The neutral phrasing of
   * the intent question is part of the rule that intent is never inferred, and
   * it belongs with the agent that enforces the rule.
   */
  async extractProfile(transcript: string): Promise<OnboardingTurn> {
    const result = await call<Extraction & { followUp: string | null }>(
      "/onboarding/extract",
      { method: "POST", body: JSON.stringify({ transcript }) },
    );
    return {
      chips: chipsFor(result),
      followUp: result.followUp,
      unresolved: result.unresolved,
    };
  }


  subscribeToAgentEvents(onEvent: (event: AgentEvent) => void): () => void {
    // Server-Sent Events rather than polling: the backend streams the OTEL
    // spans the agents actually emitted, so the Director panel shows the trace
    // rather than an animation of one.
    const source = new EventSource(`${BASE}/events`);
    source.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as AgentEvent);
      } catch {
        // A malformed frame is not worth tearing the panel down for.
      }
    };
    // EventSource reconnects on its own; nothing to do but stop shouting.
    source.onerror = () => {};
    return () => source.close();
  }

  // --- demo controls (§8) --------------------------------------------

  async reset(seed: number): Promise<void> {
    // Awaited, and failures propagate. This used to be fire-and-forget with a
    // swallowed `.catch`, so a take could start before the server had reset —
    // and the only symptom was the previous take's state appearing in the
    // recording.
    this.encounterId = null;
    await call(`/demo/reset?seed=${seed}`, { method: "POST" });
  }

  async forceOutcome(outcome: ConsentOutcome | null): Promise<void> {
    if (outcome === null) return;
    await call("/demo/force-outcome", {
      method: "POST",
      body: JSON.stringify({ outcome }),
    });
  }

  async advanceDays(days: number): Promise<void> {
    // Now real. The lock-in store moved onto `SparkSession`, so this drives the
    // actual Continuity Agent: a lock-in goes quiet on the same threshold the
    // simulation uses, and a week-five brief says something different from a
    // week-one one. It used to throw, because a demo control that appears to
    // work and does not is worse than one that is absent.
    await call(`/demo/advance-days?days=${days}`, { method: "POST" });
  }
}
