/**
 * /call — milestone 3's acceptance test.
 *
 * The headline assertion is invariant 4: there is no extend control, and the
 * call routes onward on its own when the time runs out. That is checked by
 * sweeping every interactive element on the screen for anything that could add
 * time, rather than by trusting that nobody adds a button later.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Call from "../screens/Call";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import { useSpark } from "../store/useSpark";
import { scanForIdentityFields, scanForLocation } from "./scanners";

/** Drives `performance.now()` so three minutes pass in milliseconds. */
class FakeClock {
  private t = 0;
  install() {
    vi.spyOn(performance, "now").mockImplementation(() => this.t);
    // rAF fires immediately; the screen reads the clock, not the frame rate.
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) =>
      setTimeout(() => cb(this.t), 0) as unknown as number,
    );
    vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  }
  advance(seconds: number) {
    this.t += seconds * 1000;
  }
}

let clock: FakeClock;

function renderCall() {
  return render(
    <MemoryRouter
      initialEntries={["/call"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/call" element={<Call />} />
        <Route path="/call/consent" element={<div>CONSENT SCREEN</div>} />
        <Route path="/encounter/closed" element={<div>CLOSED SCREEN</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  const adapter = new MockAdapter();
  adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
  // Enter the call the way a person does: by having accepted an encounter.
  // `/call` is guarded now (routes/guard.ts), and a fresh store is redirected —
  // which is the point, so the setup states the precondition rather than the
  // screen quietly accepting anyone who arrives.
  useSpark.getState().setClientState("PENDING_ACCEPT");
  clock = new FakeClock();
  clock.install();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setAdapter(null);
});

// ---------------------------------------------------------------------------
// INVARIANT 4 — the 180-second stop is absolute
// ---------------------------------------------------------------------------

describe("invariant 4 — no extend, hard stop at 180s", () => {
  it("offers no control that could add time", async () => {
    const { container } = renderCall();
    await screen.findByText(/ends automatically/i);

    // Sweep every interactive element for anything that could extend the call.
    // Checked by scanning the rendered output rather than by asserting the
    // absence of one known button: the failure mode is a control someone adds
    // later, under a name this test has never heard of.
    const interactive = container.querySelectorAll(
      "button, a, input, [role='button'], [role='slider']",
    );
    const banned = /extend|add time|more time|continue|keep talking|prolong|snooze|\+\s*\d*\s*(min|sec)/i;

    for (const el of interactive) {
      const description = [
        el.textContent ?? "",
        el.getAttribute("aria-label") ?? "",
        el.getAttribute("title") ?? "",
        el.getAttribute("name") ?? "",
      ].join(" ");
      expect(description, `control: ${description.trim()}`).not.toMatch(banned);
    }

    // And nothing in the copy offers it either.
    expect(container.textContent ?? "").not.toMatch(banned);
  });

  it("counts down from 3:00 and ends itself", async () => {
    renderCall();
    expect(await screen.findByText("3:00")).toBeInTheDocument();

    clock.advance(60);
    await waitFor(() => expect(screen.getByText("2:00")).toBeInTheDocument());

    clock.advance(119);
    await waitFor(() => expect(screen.getByText("0:01")).toBeInTheDocument());

    // The call ends because the time ran out — nothing was pressed.
    clock.advance(1);
    await waitFor(() =>
      expect(screen.getByText("CONSENT SCREEN")).toBeInTheDocument(),
    );
  });

  it("warms the ring in the last thirty seconds without an alarm", async () => {
    renderCall();
    await screen.findByText("3:00");
    expect(screen.getByText(/remaining/i)).toBeInTheDocument();

    clock.advance(151);
    await waitFor(() =>
      expect(screen.getByText(/wrapping up/i)).toBeInTheDocument(),
    );
    // A tone change, not a warning. §5.4: "No alarm sound."
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("marks the encounter connected, then ended — never past the gate", async () => {
    renderCall();
    await waitFor(() =>
      expect(useSpark.getState().clientState).toBe("CONNECTED"),
    );

    clock.advance(181);
    await waitFor(() =>
      expect(useSpark.getState().clientState).toBe("CALL_ENDED"),
    );
    // The call screen does not decide the outcome. It hands over to the gate.
    expect(useSpark.getState().revealed).toBeNull();
    expect(useSpark.getState().consentOutcome).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 2 — nothing identifying during the call
// ---------------------------------------------------------------------------

describe("invariant 2 — no identity during the call", () => {
  it("renders a pseudonymous handle and nothing more", async () => {
    const { container } = renderCall();
    await screen.findByText(/ends automatically/i);

    const text = container.textContent ?? "";
    expect(text).toContain("azure-heron");

    // The revealed identity for this encounter, which must not appear here.
    expect(text).not.toContain("Belen");
    expect(text).not.toContain("Brackley");

    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(scanForIdentityFields(useSpark.getState().card)).toHaveLength(0);
  });

  it("renders no location anywhere on the screen", async () => {
    const { container } = renderCall();
    await screen.findByText(/ends automatically/i);
    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// The Communication Agent's suggestion
// ---------------------------------------------------------------------------

describe("the grounded prompt", () => {
  it("appears during a stall and withdraws afterwards", async () => {
    renderCall();
    await screen.findByText("3:00");

    // Nothing suggested while people are talking.
    clock.advance(20);
    await waitFor(() => expect(screen.getByText("2:40")).toBeInTheDocument());
    expect(screen.queryByText(/suggested/i)).toBeNull();

    // The first scripted stall is at 50s.
    clock.advance(31);
    await waitFor(() =>
      expect(screen.getByText(/suggested/i)).toBeInTheDocument(),
    );

    // It is a suggestion, not a takeover — the call keeps running underneath.
    expect(screen.getByText("2:09")).toBeInTheDocument();

    // And it withdraws rather than sitting there for the rest of the call.
    clock.advance(20);
    await waitFor(() => expect(screen.queryByText(/suggested/i)).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

describe("controls", () => {
  it("offers mute and speaker, and both are visual only", async () => {
    renderCall();
    await screen.findByText(/ends automatically/i);
    expect(screen.getByLabelText("Mute")).toBeInTheDocument();
    expect(screen.getByLabelText("Speaker off")).toBeInTheDocument();
  });

  it("offers a discreet, unlabelled Guardian affordance", async () => {
    renderCall();
    await screen.findByText(/ends automatically/i);
    const guardian = screen.getByLabelText("Guardian");
    // Unremarkable to an observer: no text, no icon that announces itself.
    expect(guardian.textContent).toBe("");
    // INVARIANT 6: styled as in-app, never as system chrome.
    expect(guardian.className).not.toMatch(/system|ios|android|notification/i);
  });
});

// ---------------------------------------------------------------------------
// Leaving early — a stated safety mitigation that had not been built
// ---------------------------------------------------------------------------

describe("either party can end the call", () => {
  // ARCHITECTURE §13.8 and docs/PILOT.md both justify the absence of audio
  // screening by listing structural mitigations, one of which is "either party
  // can end it". It was documented and not implemented, which made the safety
  // argument false rather than merely incomplete. A three-minute maximum must
  // not be a three-minute minimum.

  it("offers an end-call control", async () => {
    renderCall();
    expect(await screen.findByRole("button", { name: /end call/i })).toBeVisible();
  });

  it("ends immediately, without waiting out the clock", async () => {
    renderCall();
    const end = await screen.findByRole("button", { name: /end call/i });

    clock.advance(20);                       // twenty seconds in, not 180
    fireEvent.click(end);

    await waitFor(() => {
      expect(screen.getByText("CONSENT SCREEN")).toBeInTheDocument();
    });
  });

  it("lands in exactly the same place the timer does", async () => {
    // The two exits share one function, so nothing downstream — and therefore
    // nobody on the other side — can tell an early end from a hard stop.
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /end call/i }));
    await waitFor(() => screen.getByText("CONSENT SCREEN"));
    const early = useSpark.getState().clientState;

    // Now the timer path, from a clean mount — re-entered the same way, since
    // `reset()` returns the store to IDLE and the guard would send it home.
    useSpark.getState().reset();
    useSpark.getState().setClientState("PENDING_ACCEPT");
    clock = new FakeClock();
    clock.install();
    renderCall();
    await screen.findByText(/ends automatically/i);
    clock.advance(181);
    await waitFor(() => screen.getAllByText("CONSENT SCREEN").length > 0);

    expect(early).toBe(useSpark.getState().clientState);
    expect(early).toBe("CALL_ENDED");
  });

  it("cannot be used to add time", async () => {
    // The only direction this control moves the clock is earlier. Asserted by
    // the fact that it leaves the screen: there is no state in which pressing
    // it returns to the call.
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /end call/i }));
    await waitFor(() => screen.getByText("CONSENT SCREEN"));
    expect(screen.queryByRole("button", { name: /end call/i })).toBeNull();
  });
});

describe("a call script that cannot be played", () => {
  it("says so rather than sitting blank", async () => {
    // Every frame indexes `ticks`; `ticks[0]` on an empty array is how a blank
    // screen becomes a crash mid-recording.
    const empty = new MockAdapter();
    empty.getCallScript = async () => ({ ticks: [], prompts: [] });
    setAdapter(empty);

    renderCall();
    expect(await screen.findByText(/could not be started/i)).toBeVisible();
    expect(screen.getByText(/came back empty/i)).toBeVisible();
  });

  it("surfaces an adapter failure instead of hanging", async () => {
    const broken = new MockAdapter();
    broken.getCallScript = async () => {
      throw new Error("the backend is unreachable");
    };
    setAdapter(broken);

    renderCall();
    expect(await screen.findByText(/could not be started/i)).toBeVisible();
    expect(screen.getByText(/unreachable/i)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Guardian — INVARIANT 6
// ---------------------------------------------------------------------------

describe("Guardian", () => {
  // CLAUDE.md: "Do not make Guardian Mode imitate a system or OS-level alert.
  // It is a safety feature, not a deception tool." The affordance existed on
  // this screen for three milestones without doing anything, which for a safety
  // feature is worse than not having one — it is a button someone might rely on.

  it("offers a discreet, unlabelled trigger", async () => {
    renderCall();
    const trigger = await screen.findByRole("button", { name: /guardian/i });
    // Unremarkable to a shoulder: no text, no icon with a meaning.
    expect(trigger.textContent).toBe("");
  });

  it("shows an in-app reminder, never system chrome", async () => {
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /guardian/i }));

    const dialog = await screen.findByRole("dialog");
    // It says whose reminder it is, in the product's own voice.
    expect(within(dialog).getByText(/spark · your reminder/i)).toBeInTheDocument();

    const text = dialog.textContent ?? "";
    for (const impersonation of [
      /incoming call/i, /slide to answer/i, /unknown number/i,
      /low battery/i, /battery/i, /system/i, /iphone/i, /android/i,
      /carrier/i, /no caller id/i, /alarm/i, /calendar alert/i,
    ]) {
      expect(text, `Guardian imitates "${impersonation}"`).not.toMatch(
        impersonation,
      );
    }
  });

  it("ends the call and then checks in privately", async () => {
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /guardian/i }));
    fireEvent.click(await screen.findByRole("button", { name: /step away now/i }));

    // The check-in follows the exit, on the same screen — navigating first
    // would unmount it before it could be answered.
    expect(await screen.findByText(/are you all right/i)).toBeInTheDocument();
    // And it says, before they answer, that nothing reaches the other person.
    expect(screen.getByText(/the other person is not told/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /i am fine/i }));
    await waitFor(() => {
      expect(screen.getByText("CONSENT SCREEN")).toBeInTheDocument();
    });
  });

  it("can be dismissed without ending the call", async () => {
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /guardian/i }));
    fireEvent.click(await screen.findByRole("button", { name: /not now/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Guardian's check-in has to mean something
// ---------------------------------------------------------------------------

describe("the Guardian check-in has two different answers", () => {
  // Both buttons were wired to the same handler, so "something felt off" and
  // "I am fine" did exactly the same thing. That is the worst kind of question
  // to ask someone who has just used a safety feature: it looks like it is
  // listening and it is not.

  async function stepAwayAndCheckIn() {
    renderCall();
    fireEvent.click(await screen.findByRole("button", { name: /guardian/i }));
    fireEvent.click(await screen.findByRole("button", { name: /step away now/i }));
    await screen.findByText(/are you all right/i);
  }

  it("goes on to the gate when they are fine", async () => {
    await stepAwayAndCheckIn();
    fireEvent.click(screen.getByRole("button", { name: /i am fine/i }));

    await waitFor(() => {
      expect(screen.getByText("CONSENT SCREEN")).toBeInTheDocument();
    });
    expect(useSpark.getState().guardianConcern).toBe(false);
  });

  it("closes the encounter without opening the gate when something felt off", async () => {
    // The consequence: there is no path from a flagged encounter to exchanging
    // names, because the question is never asked.
    await stepAwayAndCheckIn();
    fireEvent.click(screen.getByRole("button", { name: /something felt off/i }));

    await waitFor(() => {
      expect(screen.getByText("CLOSED SCREEN")).toBeInTheDocument();
    });
    expect(screen.queryByText("CONSENT SCREEN")).toBeNull();
    expect(useSpark.getState().guardianConcern).toBe(true);
    expect(useSpark.getState().revealed).toBeNull();
  });

  it("says what will happen before they answer", async () => {
    await stepAwayAndCheckIn();
    expect(
      screen.getByText(/we will not ask whether you want to swap names/i),
    ).toBeInTheDocument();
  });
});
