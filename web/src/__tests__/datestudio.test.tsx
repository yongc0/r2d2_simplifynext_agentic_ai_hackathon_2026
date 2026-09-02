/**
 * Date Studio — the planner, the memory panel, and the boundaries around both.
 *
 * The retention loop this covers is: pick a connection, set constraints, get
 * three grounded options, reject one with a reason, see the next set change,
 * save one, then read and correct exactly what Spark learned.
 *
 * Two things are asserted that are not features:
 *
 *   REMEMBERING IS OPT-IN. The tickbox defaults to off, and nothing is stored
 *   without it. "I am tired tonight" is context; a system that promotes it into
 *   a durable belief will be wrong about someone forever without ever having
 *   been told anything untrue.
 *
 *   THE SAFETY BOUNDARY OUTRANKS THE FEATURE. No plan and no name may appear
 *   without an eligible lock-in, whatever URL is typed.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import DateStudio from "../screens/DateStudio";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import { useSpark } from "../store/useSpark";
import { scanForLocation } from "./scanners";

let adapter: MockAdapter;
const LOCK_IN = "lock-78f62d9d60cf";

beforeEach(async () => {
  adapter = new MockAdapter();
  await adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
});

afterEach(() => setAdapter(null));

/** Take the pair all the way to a mutual reveal, which is what opens planning. */
async function connect() {
  await adapter.respondToEncounter("e", true);
  await adapter.submitConsent("e", true);
}

function renderApp(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}

/** The studio alone, so a test does not depend on navigating to it. */
function renderStudio() {
  return render(
    <MemoryRouter
      initialEntries={[`/plans/${LOCK_IN}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/plans/:lockInId" element={<DateStudio />} />
        <Route path="/plans" element={<div>PLANS HUB</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function generate() {
  fireEvent.click(await screen.findByRole("button", { name: /generate plans/i }));
  await waitFor(() =>
    expect(screen.getAllByRole("button", { name: /^save$/i }).length).toBeGreaterThan(0),
  );
}

// ---------------------------------------------------------------------------
// The hub
// ---------------------------------------------------------------------------

describe("/plans", () => {
  it("explains itself when there is nobody to plan with", async () => {
    renderApp("/plans");
    expect(
      await screen.findByText(/planning opens once you and someone else/i),
    ).toBeInTheDocument();
    // And it does not offer a feed as a consolation. Checked as OFFERS —
    // buttons and links — because the copy legitimately uses the word
    // "browse" to say there is nothing to browse.
    expect(screen.queryByRole("button", { name: /discover|browse|nearby/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /discover|browse|nearby/i })).toBeNull();
  });

  it("lists a connection once both have said yes", async () => {
    await connect();
    renderApp("/plans");
    expect(await screen.findByText("Belen Brackley")).toBeInTheDocument();
    expect(screen.getByText(/plan something/i)).toBeInTheDocument();
  });

  it("shows why a connection cannot be planned with, rather than hiding it", async () => {
    // Hiding it would leave someone wondering where a person went.
    await connect();
    const released = new MockAdapter();
    await released.reset(42);
    await released.respondToEncounter("e", true);
    await released.submitConsent("e", true);
    released.getPlanLockIns = async () => [
      {
        lockInId: LOCK_IN,
        person: {
          personId: "u001", displayName: "Belen Brackley",
          avatarSeed: "azure-heron", sharedInterests: [],
        },
        state: "released",
        unavailableReason: "This connection has been released.",
      },
    ];
    setAdapter(released);

    renderApp("/plans");
    expect(await screen.findByText(/has been released/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The form
// ---------------------------------------------------------------------------

describe("the planner form", () => {
  it("works entirely without typing", async () => {
    await connect();
    const { container } = renderStudio();
    await screen.findByRole("button", { name: /generate plans/i });

    // Every constraint is a button. The only input on the screen is the
    // remember tickbox, which is also not typing.
    const text = container.querySelectorAll(
      'input[type="text"], textarea, [contenteditable="true"]',
    );
    expect(text).toHaveLength(0);

    for (const label of [/^easy$/i, /^free$/i, /^an hour$/i, /^low$/i]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("announces selection to a screen reader, not only with colour", async () => {
    await connect();
    renderStudio();
    const easy = await screen.findByRole("button", { name: /^easy$/i });

    expect(easy).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(easy);
    expect(easy).toHaveAttribute("aria-pressed", "true");
  });

  it("lets a chosen option be unchosen", async () => {
    // "No opinion" has to be reachable, or the first tap becomes permanent.
    await connect();
    renderStudio();
    const free = await screen.findByRole("button", { name: /^free$/i });

    fireEvent.click(free);
    expect(free).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(free);
    expect(free).toHaveAttribute("aria-pressed", "false");
  });

  it("offers only times the pair genuinely share", async () => {
    // A time only one of them is free is not a choice; it is a plan neither
    // can attend. The list is server-supplied.
    await connect();
    renderStudio();
    await screen.findByRole("button", { name: /generate plans/i });

    const prefs = await adapter.getDatePreferences(LOCK_IN);
    for (const bucket of prefs.sharedBuckets) {
      expect(
        screen.getByRole("button", { name: new RegExp(`^${bucket}$`, "i") }),
      ).toBeInTheDocument();
    }
  });
});

// ---------------------------------------------------------------------------
// Remembering is opt-in
// ---------------------------------------------------------------------------

describe("what gets remembered", () => {
  it("does not remember tonight's constraints by default", async () => {
    await connect();
    renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: /^free$/i }));
    await generate();

    expect(await adapter.getDateMemory(LOCK_IN)).toEqual([]);
  });

  it("remembers only when asked, and marks it as told rather than inferred", async () => {
    await connect();
    renderStudio();

    fireEvent.click(await screen.findByRole("button", { name: /^free$/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /remember this/i }));
    await generate();

    const memory = await adapter.getDateMemory(LOCK_IN);
    expect(memory.map((m) => [m.dimension, m.value])).toContainEqual([
      "budget", "free",
    ]);
    expect(memory[0].source).toBe("explicit");
    expect(memory[0].confidence).toBe(1);
  });

  it("says so when it has prefilled from memory", async () => {
    // A preference nobody noticed being applied is one they cannot correct.
    await connect();
    await adapter.generateDatePlans(LOCK_IN, { budget: "free", remember: true });

    renderStudio();
    expect(
      await screen.findByText(/we have filled in what you usually pick/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The plans
// ---------------------------------------------------------------------------

describe("the three plans", () => {
  it("binds every selected path to its actual shared interest, not the first venue", async () => {
    await connect();
    const plan = await adapter.generateDatePlans(LOCK_IN, {});
    expect(plan.paths.length).toBeGreaterThan(1);

    for (const path of plan.paths) {
      const result = await adapter.createItinerary(LOCK_IN, {
        pathId: path.pathId,
        timeBucket: path.proposedBucket,
      });
      expect(result.itinerary, `${path.pathId}: ${result.reason}`).not.toBeNull();
      expect(result.itinerary!.groundedIn).toEqual(path.groundedIn);
      expect(result.itinerary!.stops[0].rationale.toLowerCase()).toContain(
        path.groundedIn[0],
      );
      // Coffee and birdwatching cannot honestly select a gym. The old binder
      // did exactly that because gyms happened to be first in the OSM export.
      expect(result.itinerary!.stops[0].venueName).not.toMatch(/gym|fitness/i);
    }
  });

  it("can select an active venue when swimming is genuinely shared", async () => {
    await adapter.updateProfile({
      interests: ["swimming"],
      availabilityWindow: ["evening"],
    });
    await connect();

    const plan = await adapter.generateDatePlans(LOCK_IN, { energy: "high" });
    expect(plan.paths).toHaveLength(1);
    expect(plan.paths[0].groundedIn).toEqual(["swimming"]);

    const result = await adapter.createItinerary(LOCK_IN, {
      pathId: plan.paths[0].pathId,
      energy: "high",
      timeBucket: "evening",
    });
    expect(result.itinerary, result.reason).not.toBeNull();
    expect(result.itinerary!.stops[0].venueName).toMatch(/gym|fitness/i);
    expect(result.itinerary!.stops[0].rationale).toMatch(/both mentioned swimming/i);
  });

  it("carries explicit budget, duration and energy into the real itinerary", async () => {
    await connect();
    const preferences = {
      budget: "free" as const,
      duration: "one_hour" as const,
      energy: "low" as const,
      mood: "easy" as const,
    };
    const plan = await adapter.generateDatePlans(LOCK_IN, preferences);
    expect(plan.paths[0].durationBand).toBe("one_hour");

    const result = await adapter.createItinerary(LOCK_IN, {
      ...preferences,
      pathId: plan.paths[0].pathId,
      timeBucket: plan.paths[0].proposedBucket,
    });
    expect(result.itinerary, result.reason).not.toBeNull();
    expect(result.itinerary!.stops).toHaveLength(1);
    expect(result.itinerary!.stops[0].durationMinutes).toBe(60);
    expect(result.itinerary!.stops[0].costBand).toBe("free");
    expect(result.itinerary!.stops[0].venueName).not.toMatch(/gym|fitness/i);
  });

  it("offers no invented plan when the pair share no interests", async () => {
    await adapter.updateProfile({ interests: ["climbing"] });
    await connect();

    const plan = await adapter.generateDatePlans(LOCK_IN, {});
    expect(plan.paths).toEqual([]);
    expect(plan.note).toMatch(/nothing you have both mentioned/i);
  });

  it("renders three distinct shapes", async () => {
    await connect();
    renderStudio();
    await generate();

    for (const label of [/^easy$/i, /something new/i, /keep it light/i]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("shows the evidence behind each one", async () => {
    await connect();
    renderStudio();
    fireEvent.click(await screen.findByRole("button", { name: /^free$/i }));
    await generate();

    // The rationale cites what actually scored — the shared interest, and the
    // constraint that was asked for.
    expect(screen.getAllByText(/you have both mentioned/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/you asked for something free/i).length).toBeGreaterThan(0);
  });

  it("labels a commercial partner beside the stop", async () => {
    await connect();
    renderStudio();
    await generate();

    const plan = await adapter.generateDatePlans(LOCK_IN, {});
    const partners = plan.paths
      .flatMap((p) => p.stops)
      .filter((s) => s.isCommercialPartner);
    if (partners.length > 0) {
      expect(screen.getAllByText(/spark partner/i).length).toBeGreaterThan(0);
    }
  });

  it("renders no location anywhere", async () => {
    // INVARIANT 1. A date plan is the one thing allowed to point somewhere,
    // and it is safe only because nothing here can become a map.
    await connect();
    const { container } = renderStudio();
    await generate();

    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
    expect(container.innerHTML).not.toMatch(/maps?\.google|<iframe/i);
  });

  it("never asks how the date went", async () => {
    // Spark grades the RECOMMENDATION, never the relationship. A product that
    // scores whether somebody liked you teaches people to perform.
    await connect();
    const { container } = renderStudio();
    await generate();

    const text = container.textContent ?? "";
    for (const forbidden of [
      /did they like/i, /how did it go/i, /rate .*date/i, /was it a success/i,
      /compatib/i, /% match/i,
    ]) {
      expect(text).not.toMatch(forbidden);
    }
  });
});

// ---------------------------------------------------------------------------
// Feedback and adaptation
// ---------------------------------------------------------------------------

describe("feedback", () => {
  it("records a save once", async () => {
    await connect();
    renderStudio();
    await generate();

    const saves = screen.getAllByRole("button", { name: /^save$/i });
    fireEvent.click(saves[0]);
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /^saved$/i }).length).toBe(1),
    );
  });

  it("asks why before recording a rejection", async () => {
    await connect();
    renderStudio();
    await generate();

    fireEvent.click(screen.getAllByRole("button", { name: /not for us/i })[0]);
    expect(await screen.findByText(/what was wrong with it/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /too expensive/i })).toBeInTheDocument();
  });

  it("changes the next set after a rejection", async () => {
    // The whole point of the feature, through the UI.
    await connect();
    renderStudio();
    await generate();

    const before = screen.getAllByRole("article").map((a) => a.textContent);
    fireEvent.click(screen.getAllByRole("button", { name: /not for us/i })[0]);
    fireEvent.click(await screen.findByRole("button", { name: /too long/i }));

    await waitFor(() => {
      const after = screen.getAllByRole("article").map((a) => a.textContent);
      expect(after).not.toEqual(before);
    });
  });

  it("learns a lock-in scoped preference from a reason", async () => {
    await connect();
    renderStudio();
    await generate();

    fireEvent.click(screen.getAllByRole("button", { name: /not for us/i })[0]);
    fireEvent.click(await screen.findByRole("button", { name: /too expensive/i }));

    await waitFor(async () => {
      const memory = await adapter.getDateMemory(LOCK_IN);
      const learned = memory.find((m) => m.source === "feedback");
      expect(learned).toBeDefined();
      // An inference never reaches the confidence of something you were told.
      expect(learned!.confidence).toBeLessThan(1);
    });
  });
});

// ---------------------------------------------------------------------------
// The memory panel
// ---------------------------------------------------------------------------

describe("what Spark remembers", () => {
  it("shows whether each item was told or inferred", async () => {
    await connect();
    await adapter.generateDatePlans(LOCK_IN, { budget: "free", remember: true });

    renderStudio();
    const panel = await screen.findByLabelText(/what spark remembers/i);
    expect(within(panel).getByText(/you told us/i)).toBeInTheDocument();
  });

  it("can correct a remembered value", async () => {
    await connect();
    await adapter.generateDatePlans(LOCK_IN, { budget: "free", remember: true });

    renderStudio();
    const panel = await screen.findByLabelText(/what spark remembers/i);
    fireEvent.click(within(panel).getByRole("button", { name: /change/i }));
    fireEvent.click(await within(panel).findByRole("button", { name: /under 50/i }));

    await waitFor(async () => {
      const memory = await adapter.getDateMemory(LOCK_IN);
      expect(memory.find((m) => m.dimension === "budget")?.value).toBe("under_50");
    });
  });

  it("can delete a remembered value, and it stops being remembered", async () => {
    // Deletion has to mean something, or the panel is decoration.
    await connect();
    await adapter.generateDatePlans(LOCK_IN, { budget: "free", remember: true });

    renderStudio();
    const panel = await screen.findByLabelText(/what spark remembers/i);
    fireEvent.click(within(panel).getByRole("button", { name: /forget this/i }));

    await waitFor(async () => {
      expect(await adapter.getDateMemory(LOCK_IN)).toEqual([]);
    });
  });

  it("says plainly when there is nothing yet", async () => {
    await connect();
    renderStudio();
    const panel = await screen.findByLabelText(/what spark remembers/i);
    expect(within(panel).getByText(/nothing yet/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The boundary
// ---------------------------------------------------------------------------

describe("planning is post-reveal only", () => {
  it("offers no plan before a mutual yes", async () => {
    // No `connect()` — the pair have not both said yes.
    renderStudio();
    await screen.findByRole("button", { name: /generate plans/i });
    fireEvent.click(screen.getByRole("button", { name: /generate plans/i }));

    expect(
      await screen.findByText(/opens once you have both said yes/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });

  it("renders no name on a direct link without a reveal", async () => {
    const { container } = renderStudio();
    await screen.findByRole("button", { name: /generate plans/i });
    expect(container.textContent).not.toMatch(/Belen Brackley/);
  });
});
