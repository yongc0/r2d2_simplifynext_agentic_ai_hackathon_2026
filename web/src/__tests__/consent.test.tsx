/**
 * /encounter and /call/consent — milestone 4's acceptance test.
 *
 * The headline is INVARIANT 3: a decline produces an identical screen either
 * way. Asserted by actually driving all three non-mutual endings through the
 * real component and diffing the rendered DOM, rather than by reading the copy
 * and agreeing that it looks the same.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Consent, { revealAt } from "../screens/Consent";
import Encounter from "../screens/Encounter";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import { CLOSE_OUT_DELAY_MS } from "../components/CloseOut";
import type { ConsentOutcome } from "../api/types";
import { useSpark } from "../store/useSpark";
import { scanForIdentityFields, scanForLocation } from "./scanners";

let adapter: MockAdapter;

beforeEach(async () => {
  adapter = new MockAdapter();
  await adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
  setAdapter(null);
});

function renderConsent() {
  // The gate opens because a call ended. `/call/consent` is guarded, and this
  // is the state the two exits from `/call` leave behind — stated here so the
  // precondition is visible rather than assumed.
  useSpark.getState().setClientState("CALL_ENDED");
  return render(
    <MemoryRouter
      initialEntries={["/call/consent"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/call/consent" element={<Consent />} />
        <Route path="/reveal" element={<div>REVEAL SCREEN</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEncounter() {
  return render(
    <MemoryRouter
      initialEntries={["/encounter"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/encounter" element={<Encounter />} />
        <Route path="/encounter/waiting" element={<div>WAITING</div>} />
        <Route path="/encounter/closed" element={<div>CLOSED ROUTE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/**
 * Drive one ending to completion and return the close screen's markup.
 *
 * `forced` is how the demo controls film each branch; the point of this helper
 * is that the caller varies it and the RESULT must not change.
 */
async function closeOutMarkupFor(
  forced: ConsentOutcome,
  userSays: boolean,
): Promise<string> {
  await adapter.reset(42);
  await adapter.forceOutcome(forced);
  useSpark.getState().reset();

  const user = userEvent.setup();
  const { container, unmount } = renderConsent();

  await user.click(screen.getByRole("button", { name: userSays ? "Yes" : "No" }));
  await waitFor(
    () => expect(screen.getByText("That one is closed.")).toBeInTheDocument(),
    { timeout: 4000 },
  );

  const markup = container.innerHTML;
  unmount();
  return markup;
}

// ---------------------------------------------------------------------------
// INVARIANT 3 — a decline emits no observable signal
// ---------------------------------------------------------------------------

describe("invariant 3 — every non-connection ends identically", () => {
  it("renders byte-identical markup whoever declined", async () => {
    // The three ways an encounter can fail to become a connection:
    const theyDeclined = await closeOutMarkupFor("declined", true);
    const theyNeverAnswered = await closeOutMarkupFor("no_response", true);
    const iDeclined = await closeOutMarkupFor("declined", false);

    expect(theyNeverAnswered).toEqual(theyDeclined);
    expect(iDeclined).toEqual(theyDeclined);
    // Three real close-out waits back to back, deliberately not mocked: the
    // point is to diff what a person would actually have seen.
  }, 20_000);

  it("waits exactly the same time on every branch", async () => {
    // If the delay varied with the answer, the clock would say what the words
    // refuse to. Measured against the fake timer, so it is the code's timing
    // and not the machine's.
    for (const [forced, says] of [
      ["declined", true],
      ["no_response", true],
      ["declined", false],
    ] as const) {
      vi.useFakeTimers();
      await adapter.reset(42);
      await adapter.forceOutcome(forced);
      useSpark.getState().reset();

      const { unmount } = renderConsent();
      // fireEvent rather than userEvent: userEvent schedules its own timers,
      // which deadlocks against a mocked clock. The click is the only input
      // this test needs, and it is synchronous.
      // The click AND the adapter promise it starts, inside one act scope.
      // `answer()` suspends on an await, so a bare fireEvent returns before the
      // state updates land and React reports them as unwrapped.
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: says ? "Yes" : "No" }),
        );
      });

      // One tick short: nothing yet, on every branch.
      await act(async () => {
        // Advancing the clock fires the close-out timer, and that timer sets
        // state. Without act the update lands outside the test and React says
        // so on stderr — noise that hides a real warning later.
        await vi.advanceTimersByTimeAsync(CLOSE_OUT_DELAY_MS - 50);
      });
      expect(
        screen.queryByText("That one is closed."),
        `${forced}/${says} closed early`,
      ).toBeNull();

      await act(async () => {
        // Advancing the clock fires the close-out timer, and that timer sets
        // state. Without act the update lands outside the test and React says
        // so on stderr — noise that hides a real warning later.
        await vi.advanceTimersByTimeAsync(100);
      });
      expect(
        screen.getByText("That one is closed."),
        `${forced}/${says} did not close on time`,
      ).toBeInTheDocument();

      unmount();
      vi.useRealTimers();
    }
  });

  it("says nothing about the other person", async () => {
    const markup = await closeOutMarkupFor("declined", true);
    const text = markup.replace(/<[^>]+>/g, " ").toLowerCase();
    for (const leak of [
      "declin", "pending", "waiting", "they ", "other person",
      "not ready", "unfortunately", "sorry", "better luck",
    ]) {
      expect(text, `close-out mentions "${leak}"`).not.toContain(leak);
    }
  });

  it("the close screen takes no props that could carry an outcome", async () => {
    // Structural, like the Python `build_close_out` signature test. A component
    // that is never given the outcome cannot vary with it, however it is later
    // edited.
    const { CloseOut } = await import("../components/CloseOut");
    expect(CloseOut.length).toBe(0);
  });

  it("a decline at the notification reaches the same close-out", async () => {
    const user = userEvent.setup();
    renderEncounter();
    await user.click(await screen.findByRole("button", { name: "Not tonight" }));
    // Same component, reached by a different road.
    expect(await screen.findByText("CLOSED ROUTE")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The mutual path
// ---------------------------------------------------------------------------

describe("a mutual yes", () => {
  it("reveals, and only then", async () => {
    const user = userEvent.setup();
    renderConsent();

    await user.click(screen.getByRole("button", { name: "Yes" }));
    // Nothing revealed while the answer is still unknown.
    expect(useSpark.getState().revealed).toBeNull();

    await waitFor(
      () => expect(screen.getByText("REVEAL SCREEN")).toBeInTheDocument(),
      { timeout: 4000 },
    );
    expect(useSpark.getState().revealed?.displayName).toBe("Belen Brackley");
  });

  it("shows no hopeful animation while the outcome is unknown", async () => {
    const user = userEvent.setup();
    const { container } = renderConsent();
    await user.click(screen.getByRole("button", { name: "Yes" }));

    const waiting = container.textContent ?? "";
    // §5.5: "Do not animate a hopeful outcome before it is known."
    for (const hopeful of ["fingers crossed", "hoping", "match", "!", "🎉"]) {
      expect(waiting.toLowerCase()).not.toContain(hopeful);
    }
  });
});

// ---------------------------------------------------------------------------
// INVARIANTS 1 and 2 on the notification — the shot that sells the product
// ---------------------------------------------------------------------------

describe("/encounter", () => {
  it("renders the copy the spec asks for", async () => {
    renderEncounter();
    expect(
      await screen.findByText("You crossed paths today."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Someone here might be worth three minutes."),
    ).toBeInTheDocument();
    expect(screen.getByText(/your paths crossed this afternoon/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not tonight" })).toBeInTheDocument();
  });

  it("renders nothing identifying — invariant 2", async () => {
    const { container } = renderEncounter();
    await screen.findByText("You crossed paths today.");

    const text = container.textContent ?? "";
    // The identity this very encounter reveals later, which must not be here.
    expect(text).not.toContain("Belen");
    expect(text).not.toContain("Brackley");

    // No image of any kind. A blurred silhouette is forbidden too — it implies
    // an appearance, which is the judgement this product removes.
    expect(container.querySelectorAll("img, svg image, picture")).toHaveLength(0);
    expect(container.innerHTML).not.toMatch(/silhouette|avatar|blur/i);

    expect(scanForIdentityFields(useSpark.getState().card)).toHaveLength(0);
  });

  it("renders no location — invariant 1", async () => {
    const { container } = renderEncounter();
    await screen.findByText("You crossed paths today.");
    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
  });

  it("does not jump when the card arrives", async () => {
    // The card is fetched, so there is a moment before it exists. That moment
    // must reserve its space rather than collapse — this screen is on camera.
    const { container } = renderEncounter();
    const before = container.firstElementChild as HTMLElement | null;
    expect(before?.className).toContain("h-full");
    await screen.findByText("You crossed paths today.");
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 3 — a slow response must not become a channel
// ---------------------------------------------------------------------------

describe("the wait is quantised, not merely delayed", () => {
  // The delay used to start AFTER `submitConsent` resolved, so the real wait
  // was network time plus the constant — and the mutual branch does strictly
  // more work than the others. The clock could be read for the outcome before
  // the screen said anything.
  //
  // `revealAt` now measures from the click and rounds UP to a whole window, so
  // the outcome always appears on a multiple of the delay.

  it("shows the outcome on a multiple of the delay, whatever the response took", () => {
    for (const elapsed of [0, 1, 100, 2599, 2600, 2601, 3000, 5199, 9000]) {
      vi.spyOn(performance, "now").mockReturnValue(elapsed);
      const wait = revealAt(0);
      const total = elapsed + wait;

      expect(wait, `elapsed ${elapsed}ms`).toBeGreaterThanOrEqual(0);
      expect(total % CLOSE_OUT_DELAY_MS, `elapsed ${elapsed}ms`).toBe(0);
      expect(total, `elapsed ${elapsed}ms`).toBeGreaterThanOrEqual(CLOSE_OUT_DELAY_MS);
    }
    vi.restoreAllMocks();
  });

  it("makes two responses inside the same window indistinguishable", () => {
    // The realistic case: a decline answered in 80ms and a mutual yes that took
    // 2.1s — both land at 2,600ms, so the difference is not on screen at all.
    const totals = [80, 2100].map((elapsed) => {
      vi.spyOn(performance, "now").mockReturnValue(elapsed);
      const total = elapsed + revealAt(0);
      vi.restoreAllMocks();
      return total;
    });
    expect(totals[0]).toBe(totals[1]);
    expect(totals[0]).toBe(CLOSE_OUT_DELAY_MS);
  });
});
