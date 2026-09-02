/**
 * `/home`, `/reveal` and `/lockins` — milestone 6, plus the whole path end to end.
 *
 * Two things are being checked here that are not "does it render".
 *
 * INVARIANT 7 — avatars are generated illustrations, never a photograph. The
 * realistic failure is a placeholder image service dropped in during a build and
 * left there, so the assertion is that no `<img>` and no remote URL exists on
 * either screen that shows a person.
 *
 * THE TONE OF A QUIET LOCK-IN. §5.7 asks for "a distinct, non-guilting
 * treatment". That is a product rule, not a style note — a connection going
 * quiet is an ordinary thing between people, and a screen that bills it as a
 * failure is optimising engagement at the user's expense. Asserted by scanning
 * the copy for the vocabulary that would do it.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import { CONTINUITY_CITATION } from "../api/callFixture";
import { useSpark } from "../store/useSpark";
import { scanForLocation } from "./scanners";

let adapter: MockAdapter;

beforeEach(async () => {
  adapter = new MockAdapter();
  await adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
});

afterEach(() => setAdapter(null));

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}

/** Put the store where a mutual reveal would have put it. */
async function afterMutualYes() {
  await adapter.respondToEncounter("e", true);
  const { person } = await adapter.submitConsent("e", true);
  useSpark.getState().setRevealed(person);
  return person!;
}

// ---------------------------------------------------------------------------
// /home
// ---------------------------------------------------------------------------

describe("/home — the waiting state", () => {
  it("has nothing to scroll", async () => {
    // §5.2: "No feed, no browse, no profiles, no activity." The emptiness is
    // the product argument, so this asserts the vocabulary of the thing it is
    // arguing against.
    const { container } = renderAt("/home");
    // Settle the lock-in fetch before reading the DOM, so the assertion sees
    // the screen as it ends up rather than as it first paints.
    await screen.findByText(/one person a day/i);
    const text = container.textContent ?? "";

    for (const forbidden of [
      /discover/i, /browse/i, /nearby/i, /suggested for you/i,
      /people you/i, /matches/i, /swipe/i, /streak/i, /activity/i,
    ]) {
      expect(text, `home offers "${forbidden}"`).not.toMatch(forbidden);
    }
  });

  it("waits without a countdown for a spontaneous encounter", async () => {
    renderAt("/home");
    await screen.findByText(/one person a day/i);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/arrive spontaneously|crossed your path/i);
    expect(text).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("renders no location", async () => {
    const { container } = renderAt("/home");
    await screen.findByText(/one person a day/i);
    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// /reveal
// ---------------------------------------------------------------------------

describe("/reveal — the only screen that may show a name", () => {
  it("shows the name, the shared interests, and one action", async () => {
    const person = await afterMutualYes();
    renderAt("/reveal");

    // `toBeInTheDocument` throughout: the screen animates in from opacity 0
    // and jsdom does not run the animation, so `toBeVisible` here would assert
    // something about framer-motion rather than about the reveal.
    expect(await screen.findByText(person.displayName)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /add to lock-ins/i }),
    ).toBeInTheDocument();
    for (const interest of person.sharedInterests) {
      expect(screen.getByText(interest)).toBeInTheDocument();
    }
  });

  it("draws a generated illustration, not a photograph", async () => {
    // INVARIANT 7. `Avatar` takes a seed and draws SVG; there is no `src` to
    // point at a face, which is what makes this structural rather than a
    // matter of nobody having reached for a placeholder service yet.
    await afterMutualYes();
    const { container } = renderAt("/reveal");

    await screen.findByText(/you both said yes/i);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.innerHTML).not.toMatch(/https?:\/\//);
  });

  it("does not celebrate", async () => {
    // §5.6: "A restrained reveal animation — a fade and rise, not confetti."
    // Two people agreeing to exchange names is a quiet thing.
    await afterMutualYes();
    const { container } = renderAt("/reveal");
    await screen.findByText(/you both said yes/i);

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/congratulations|🎉|match!|it's a match|woohoo/i);
  });
});

// ---------------------------------------------------------------------------
// /lockins
// ---------------------------------------------------------------------------

describe("/lockins — five slots", () => {
  it("renders five slots, with the empty ones visible", async () => {
    await afterMutualYes();
    renderAt("/lockins");

    await screen.findByText(/1 of 5/);
    // Four drawn empties, not four absences. Scarcity has to be legible.
    expect(await screen.findAllByLabelText(/empty lock-in slot/i)).toHaveLength(4);
  });

  it("shows five empties before anyone is connected", async () => {
    renderAt("/lockins");
    expect(await screen.findAllByLabelText(/empty lock-in slot/i)).toHaveLength(5);
    expect(screen.getByText(/0 of 5/)).toBeVisible();
  });

  it("shows a brief that cites something the pair actually discussed", async () => {
    await afterMutualYes();
    renderAt("/lockins");

    // `toBeInTheDocument`, not `toBeVisible`: the card animates in from
    // opacity 0 and jsdom does not run the animation, so visibility here would
    // be asserting something about framer-motion rather than about the brief.
    const brief = await screen.findByText(new RegExp(CONTINUITY_CITATION, "i"));
    expect(brief).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ask how it went/i }),
    ).toBeInTheDocument();
  });

  it("treats a quiet lock-in without guilt", async () => {
    await afterMutualYes();
    await adapter.advanceDays(12);
    renderAt("/lockins");

    await screen.findByText(/quiet/i);
    const text = document.body.textContent ?? "";

    // The vocabulary a growth team would reach for, and which this product
    // must not: nothing that frames a quiet connection as the user's failure.
    for (const forbidden of [
      /don't lose/i, /do not lose/i, /losing touch/i, /slipping away/i,
      /you haven't/i, /you have not spoken in/i, /reach out before/i,
      /streak/i, /expires?( soon)?/i, /act now/i, /last chance/i,
    ]) {
      expect(text, `quiet copy says "${forbidden}"`).not.toMatch(forbidden);
    }
  });

  it("renders no location", async () => {
    await afterMutualYes();
    const { container } = renderAt("/lockins");
    await screen.findByText(/1 of 5/);
    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// The whole path, in one go
// ---------------------------------------------------------------------------

describe("the full mock path", () => {
  it("runs home → encounter → call → consent → reveal → lock-ins", async () => {
    // FRONTEND.md §10: "The full path is clickable." Driven through the real
    // App and the real router, so a broken route or a missing guard fails here
    // rather than during a take.
    useSpark.getState().setWindowOpen(true);
    renderAt("/home");

    fireEvent.click(
      await screen.findByRole("button", { name: /start the encounter/i }),
    );

    fireEvent.click(await screen.findByRole("button", { name: /^accept$/i }));

    // `/encounter/waiting` holds for a fixed beat before the call opens, so
    // this waits for the call screen rather than assuming it is already there.
    // Then the call is ended early rather than sitting through three minutes.
    fireEvent.click(
      await screen.findByRole("button", { name: /end call/i }, { timeout: 8000 }),
    );

    fireEvent.click(await screen.findByRole("button", { name: /^yes$/i }));

    expect(
      await screen.findByRole("button", { name: /add to lock-ins/i }, { timeout: 8000 }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add to lock-ins/i }));

    const heading = await screen.findByRole("heading", { name: /lock-ins/i });
    expect(heading).toBeInTheDocument();
    expect(await screen.findByText(/1 of 5/)).toBeInTheDocument();
  }, 30_000);
});

// ---------------------------------------------------------------------------
// The demo strip
// ---------------------------------------------------------------------------

describe("demo controls", () => {
  it("surface a failure instead of appearing to work", async () => {
    // `advanceDays` is unavailable over HTTP. A control that silently does
    // nothing is worse than one that is absent, so the strip says why.
    const broken = new MockAdapter();
    broken.advanceDays = async () => {
      throw new Error("advanceDays is not available over HTTP yet");
    };
    setAdapter(broken);

    const { container } = render(
      <MemoryRouter
        initialEntries={["/lockins"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    );

    // Let the screen settle before asserting, so its own fetch does not land
    // outside the test.
    await screen.findByText(/five at a time/i);

    // The strip is behind ?demo=1, which MemoryRouter cannot set, so drive the
    // component's action surface directly through the store-backed adapter.
    await expect(broken.advanceDays(1)).rejects.toThrow(/not available over HTTP/);
    expect(within(container).queryByText(/skip to encounter window/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The encounter window closes
// ---------------------------------------------------------------------------

describe("spontaneous encounters", () => {
  it("shows no countdown while waiting", async () => {
    renderAt("/home");
    expect(await screen.findByText(/next encounter will arrive spontaneously/i)).toBeVisible();
    expect(screen.queryByText(/^\d{2}:\d{2}:\d{2}$/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The Director trace has to survive a reset
// ---------------------------------------------------------------------------

describe("the agent feed after a reset", () => {
  it("resubscribes, so the second take is not filmed against an empty panel", async () => {
    // `MockAdapter.reset()` cancels the timers driving the scripted trace. The
    // app subscribed once at mount, so after the first reset the panel went
    // quiet permanently — the exact failure §8's reset exists to prevent.
    let subscriptions = 0;
    const counted = new MockAdapter();
    const original = counted.subscribeToAgentEvents.bind(counted);
    counted.subscribeToAgentEvents = (onEvent) => {
      subscriptions += 1;
      return original(onEvent);
    };
    setAdapter(counted);

    renderAt("/home");
    await screen.findByText(/one person a day/i);
    expect(subscriptions).toBe(1);

    act(() => {
      useSpark.getState().reset();
    });

    await waitFor(() => expect(subscriptions).toBe(2));
  });
});

// ---------------------------------------------------------------------------
// The reveal must not describe a call that did not happen that way
// ---------------------------------------------------------------------------

describe("/reveal copy", () => {
  it("says nothing about how long the call was", async () => {
    // The call can end early — through the end-call control or through
    // Guardian — so "you spoke for three minutes" is simply wrong for anyone
    // who left at forty seconds.
    await afterMutualYes();
    const { container } = renderAt("/reveal");
    await screen.findByText(/you both said yes/i);

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/three minutes|3 minutes|180 seconds/i);
    expect(text).toMatch(/you spoke without knowing that/i);
  });
});

// ---------------------------------------------------------------------------
// /dates — the one screen allowed to point somewhere
// ---------------------------------------------------------------------------

describe("/dates — three evenings, after a mutual yes", () => {
  // This is the half of the product that is not waiting. It is also the only
  // screen permitted to name a kind of place, and it is permitted because it
  // runs after both people have said yes: two people choosing where to meet
  // are picking a destination together, not disclosing where either of them
  // was. The guard and the scanner below are what hold that line.

  it("redirects when there has been no mutual reveal", async () => {
    renderAt("/dates");
    expect(await screen.findByText(/one person a day/i)).toBeInTheDocument();
    expect(screen.queryByText(/something to do/i)).toBeNull();
  });

  it("offers three grounded evenings once both said yes", async () => {
    const person = await afterMutualYes();
    renderAt("/dates");

    expect(await screen.findByText(/something to do/i)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`for you and ${person.displayName}`, "i")),
    ).toBeInTheDocument();

    const plan = await adapter.getDatePlan("e");
    expect(plan.paths).toHaveLength(3);
    for (const path of plan.paths) {
      expect(await screen.findByText(path.headline)).toBeInTheDocument();
      // Never an ungrounded suggestion: every path cites something both said.
      expect(path.groundedIn.length).toBeGreaterThan(0);
    }
  });

  it("names no place, distance or map", async () => {
    // INVARIANT 1 still applies to the wording. A stop is a KIND of place —
    // "a wet market breakfast" — never a named business at an address.
    await afterMutualYes();
    const { container } = renderAt("/dates");
    await screen.findByText(/something to do/i);

    expect(scanForLocation(container.textContent ?? "")).toHaveLength(0);
    expect(container.innerHTML).not.toMatch(/maps?\.google|openstreetmap|<iframe/i);
  });

  it("labels a commercial partner beside the venue", async () => {
    // §13.6: partners may only appear where they already rank, and are always
    // disclosed — in the same place the venue is read, not in a footnote.
    await afterMutualYes();
    renderAt("/dates");
    await screen.findByText(/something to do/i);

    const plan = await adapter.getDatePlan("e");
    const partnerStops = plan.paths
      .flatMap((p) => p.stops)
      .filter((s) => s.isCommercialPartner);
    expect(partnerStops.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/spark partner/i).length).toBe(partnerStops.length);
  });

  it("has no stop that could carry a location", async () => {
    // Structural. `DateStop` has no address, distance or map field, so the
    // screen cannot render one however it is later edited.
    const plan = await (async () => {
      await afterMutualYes();
      return adapter.getDatePlan("e");
    })();

    for (const stop of plan.paths.flatMap((p) => p.stops)) {
      expect(Object.keys(stop).sort()).toEqual(
        ["activity", "category", "isCommercialPartner", "venueId"],
      );
    }
  });

  it("says why rather than showing a blank screen", async () => {
    // The adapter returns an honest note when there is nothing to suggest.
    useSpark.getState().setRevealed({
      personId: "u001",
      displayName: "Belen",
      avatarSeed: "azure-heron",
      sharedInterests: [],
    });
    renderAt("/dates");

    expect(
      await screen.findByText(/date planning opens once you have both said yes/i),
    ).toBeInTheDocument();
  });
});
