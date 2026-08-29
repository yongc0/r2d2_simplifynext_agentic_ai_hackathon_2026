/**
 * /onboarding — milestone 5's acceptance test.
 *
 * Two things are being asserted, and only one of them is a feature.
 *
 * The feature: extraction is live. Chips appear as the person talks, which is
 * the shot that makes the Onboarding Agent legible in three seconds.
 *
 * The rules: INVARIANT 5 (no height, appearance or photo anywhere in intake)
 * and the intent rule from ARCHITECTURE §13.1 — intent is never inferred from
 * tone. The second one is not a UI invariant, but this screen is where it would
 * break, and a warm sentence read as "casual" puts two people in front of each
 * other under a misunderstanding neither agreed to.
 *
 * `spark/tests/test_intent.py` holds the same line on the Python side with the
 * same kind of sentences.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import Onboarding from "../screens/Onboarding";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import {
  EXCLUDED_ATTRIBUTES,
  chipsFor,
  extractFromTranscript,
  namedIntents,
} from "../api/extract";
import { useSpark } from "../store/useSpark";
import { scanForLocation } from "./scanners";

beforeEach(() => {
  const adapter = new MockAdapter();
  adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
});

afterEach(() => {
  setAdapter(null);
});

function renderVerification() {
  return render(
    <MemoryRouter
      initialEntries={["/onboarding"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/home" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Advance the explicit three-screen prototype into conversational intake. */
function finishDemoVerification() {
  fireEvent.click(
    screen.getByRole("button", { name: "Verify with Singpass demo" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Approve demo verification" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Continue to profile" }),
  );
}

/** Most onboarding tests exercise extraction, whose precondition is the
 *  completed verification concept. Keep that precondition explicit here. */
function renderOnboarding() {
  const result = renderVerification();
  finishDemoVerification();
  return result;
}

/** Type into the composer and send. `fireEvent`, not `userEvent`: the screen
 *  runs real timers for the agent's pause, and userEvent's own timer handling
 *  deadlocks against them. */
async function say(text: string) {
  fireEvent.change(screen.getByLabelText("Your reply"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

/** The chip panel only — never the transcript, which echoes the user's own
 *  words back and is not something the agent produced. */
function chipPanel(): HTMLElement {
  return screen.getByLabelText("What the agent has understood");
}

// ---------------------------------------------------------------------------
// Simulated Singpass verification — concept only, never credentials
// ---------------------------------------------------------------------------

describe("Singpass verification mockup", () => {
  it("labels itself as simulated before the person can interact", () => {
    const { container } = renderVerification();

    expect(screen.getByText(/start as a verified person/i)).toBeVisible();
    expect(screen.getByText("Simulated")).toBeVisible();
    expect(screen.getByText(/no real singpass login occurs/i)).toBeVisible();
    expect(screen.getByText(/no external service is contacted/i)).toBeVisible();
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("form")).toBeNull();
    expect(container.querySelector("a[href]")).toBeNull();
  });

  it("shows the minimum disclosure and no credential entry screen", () => {
    const { container } = renderVerification();
    fireEvent.click(
      screen.getByRole("button", { name: "Verify with Singpass demo" }),
    );

    expect(screen.getByText("Age eligibility")).toBeVisible();
    expect(screen.getByText("Unique account token")).toBeVisible();
    expect(screen.getByText(/not shared with spark/i)).toBeVisible();
    expect(
      screen.getByText(/nric, full date of birth, address, photo/i),
    ).toBeVisible();
    expect(container.querySelector("input")).toBeNull();
  });

  it("can return from the disclosure without completing verification", () => {
    renderVerification();
    fireEvent.click(
      screen.getByRole("button", { name: "Verify with Singpass demo" }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Back to verification introduction",
      }),
    );

    expect(screen.getByText(/start as a verified person/i)).toBeVisible();
    expect(screen.queryByText("Age eligibility")).toBeNull();
  });

  it("hands off to conversational intake only after demo approval", () => {
    renderVerification();

    expect(screen.queryByLabelText("Your reply")).toBeNull();
    finishDemoVerification();

    expect(
      screen.getByText(/tell me a little about how you spend your time/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Your reply")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// The live extraction
// ---------------------------------------------------------------------------

describe("live chip extraction", () => {
  it("fills in the panel as the person talks", async () => {
    renderOnboarding();

    // Nothing before they say anything. The panel states that rather than
    // sitting blank, so the empty frame still reads as deliberate on camera.
    expect(chipPanel()).toHaveTextContent(/nothing yet/i);

    await say("I like coffee and hiking, and I care about honesty.");

    await waitFor(() => {
      expect(chipPanel()).toHaveTextContent("Coffee");
    });
    expect(chipPanel()).toHaveTextContent("Hiking");
    expect(chipPanel()).toHaveTextContent("Honesty");
  }, 15_000);

  it("extracts over everything said so far, not just the last message", async () => {
    renderOnboarding();

    await say("I like coffee.");
    await waitFor(() => expect(chipPanel()).toHaveTextContent("Coffee"));

    await say("I am usually free in the evenings.");
    await waitFor(() => expect(chipPanel()).toHaveTextContent("Evenings"));

    // The first turn's chip is still there. An extractor with no memory would
    // have dropped it and then asked about it again.
    expect(chipPanel()).toHaveTextContent("Coffee");
  }, 15_000);
});

// ---------------------------------------------------------------------------
// Intent is never inferred from tone (ARCHITECTURE §13.1)
// ---------------------------------------------------------------------------

describe("intent is never inferred", () => {
  it.each([
    "I want someone who really cares and is ready for a proper life together.",
    "Honestly I just want to have fun and not think too hard about it.",
    "I have been hurt before and I am ready to be serious about this.",
    "I am not really looking for anything heavy right now.",
  ])("names no intent for tone-heavy text: %j", (sentence) => {
    // The sentences that most invite a guess. Every one of them is a person
    // hinting; none of them is a person saying.
    expect(namedIntents(sentence)).toHaveLength(0);
    expect(extractFromTranscript(sentence).unresolved).toContain("intent");
  });

  it("asks, neutrally, rather than guessing", async () => {
    renderOnboarding();
    await say("I am ready to be serious about meeting the right person.");

    await waitFor(() => {
      expect(screen.getByText(/what are you hoping to find here/i)).toBeVisible();
    });

    // All three options, offered in a fixed order with none preselected and
    // none emphasised. A default here would be a nudge, and a nudge is
    // inferring intent with extra steps.
    expect(screen.getByRole("button", { name: "Something long term" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Something short term" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Friends" })).toBeVisible();

    // And nothing was captured in the meantime.
    expect(chipPanel()).not.toHaveTextContent(/long term|short term|friends/i);
  }, 15_000);

  it("sets an intent once the person names one", async () => {
    renderOnboarding();
    await say("I am free in the evenings and I like reading.");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Friends" })).toBeVisible();
    });
    fireEvent.click(screen.getByRole("button", { name: "Friends" }));

    await waitFor(() => expect(chipPanel()).toHaveTextContent("Friends"));

    // The button sent a SENTENCE, which the extractor read the ordinary way.
    // The screen has no privileged route to setting an intent, so the last
    // message in the transcript is the person saying it.
    expect(screen.getByText("I am looking to make friends.")).toBeVisible();
  }, 15_000);
});

// ---------------------------------------------------------------------------
// Availability uses the fixed backend vocabulary
// ---------------------------------------------------------------------------

describe("availability choices", () => {
  it("shows every valid time bucket and completes from one click", async () => {
    renderOnboarding();
    await say("I like coffee and I am looking for something long term.");

    const chooser = await screen.findByLabelText(
      "Choose when you are usually free",
    );
    for (const option of [
      "Early morning",
      "Morning",
      "Midday",
      "Afternoon",
      "Evening",
      "Night",
    ]) {
      expect(
        screen.getByRole("button", { name: option }),
      ).toBeVisible();
    }

    fireEvent.click(screen.getByRole("button", { name: "Evening" }));

    await waitFor(() => expect(chipPanel()).toHaveTextContent("Evening"));
    expect(chooser).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Continue" }),
    ).toBeVisible();
  }, 15_000);
});

// ---------------------------------------------------------------------------
// INVARIANT 5 — no height, appearance, or photo
// ---------------------------------------------------------------------------

describe("invariant 5 — nothing physical is ever captured", () => {
  it("offers no field for one", async () => {
    const { container } = renderOnboarding();

    // There is one input on this screen and it is a free-text reply. No file
    // picker, no camera, no upload, no range slider for a height.
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.querySelector('input[type="range"]')).toBeNull();
    expect(container.querySelector("[capture]")).toBeNull();
    expect(container.textContent ?? "").not.toMatch(EXCLUDED_ATTRIBUTES);
  });

  it("captures nothing when someone volunteers one", async () => {
    renderOnboarding();
    await say("I am 180cm and pretty athletic, and I like climbing.");

    // The interest lands; the rest of the sentence does not exist as far as
    // the profile is concerned.
    await waitFor(() => expect(chipPanel()).toHaveTextContent("Climbing"));
    expect(chipPanel().textContent ?? "").not.toMatch(EXCLUDED_ATTRIBUTES);
  }, 15_000);

  it("has no chip kind that could render one", () => {
    // Structural. Every chip the panel can show comes out of `chipsFor`, and
    // the only strings it can produce come from the fixed lists in extract.ts.
    const chips = chipsFor(
      extractFromTranscript(
        "I am tall and athletic with a good photo, and I like yoga.",
      ),
    );
    expect(chips.map((c) => c.label)).toEqual(["Yoga", "English"]);
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 1 — the panel cannot name a place, whatever is typed at it
// ---------------------------------------------------------------------------

describe("invariant 1 — intake captures no location", () => {
  it("keeps a place out of the panel even when the person types one", async () => {
    renderOnboarding();
    await say("I get coffee near Raffles Place most afternoons.");

    await waitFor(() => expect(chipPanel()).toHaveTextContent("Coffee"));

    // The transcript echoes what they said — that is their own screen, and
    // their own words. The PROFILE is what travels, and it holds a time bucket
    // and an interest, with nowhere to put the place.
    expect(scanForLocation(chipPanel().textContent ?? "")).toHaveLength(0);
    expect(chipPanel()).toHaveTextContent("Afternoons");
  }, 15_000);
});
