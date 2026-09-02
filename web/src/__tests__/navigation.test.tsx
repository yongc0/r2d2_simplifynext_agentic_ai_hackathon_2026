/**
 * Navigation and the profile — reaching every feature, and the places you must not.
 *
 * FRONTEND.md §5.2 says home is "deliberately, almost aggressively empty… no
 * feed, no browse, no profiles". That rule is about not BROWSING OTHER PEOPLE,
 * which is the product argument. Reaching your own lock-ins, your own plans and
 * your own profile does not touch it — a Discover tab would, and there isn't
 * one. The first describe below asserts that distinction rather than trusting
 * it to a comment.
 *
 * The second describe is the more important one. The nav is ABSENT during the
 * call, the consent gate, the reveal and an offered encounter, and both reasons
 * are product reasons:
 *
 *   Three minutes only works because there is nowhere else to be. A nav bar is
 *   an escape hatch.
 *
 *   The consent gate is two buttons and a genuinely uncertain wait. A third
 *   exit turns a decision into something you can wander away from, and the
 *   other person is waiting on it.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";
import { useSpark } from "../store/useSpark";

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

const nav = () => screen.queryByRole("navigation", { name: /main/i });

// ---------------------------------------------------------------------------
// Reaching everything
// ---------------------------------------------------------------------------

describe("the app is navigable", () => {
  it("offers the four places you can be", async () => {
    renderAt("/home");
    const bar = await screen.findByRole("navigation", { name: /main/i });

    for (const label of ["Home", "Plans", "Lock-ins", "You"]) {
      expect(within(bar).getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("offers no way to browse other people", async () => {
    // The rule §5.2 is actually about. A fifth tab listing strangers would
    // undo the product's whole argument; these four do not.
    renderAt("/home");
    const bar = await screen.findByRole("navigation", { name: /main/i });

    expect(within(bar).getAllByRole("link")).toHaveLength(4);
    for (const forbidden of [/discover/i, /browse/i, /nearby/i, /people/i, /matches/i]) {
      expect(within(bar).queryByRole("link", { name: forbidden })).toBeNull();
    }
  });

  it.each([
    ["Plans", /^plans$/i],
    ["Lock-ins", /^lock-ins$/i],
    ["You", /^you$/i],
  ])("reaches %s from home in one tap", async (label, heading) => {
    renderAt("/home");
    const bar = await screen.findByRole("navigation", { name: /main/i });

    fireEvent.click(within(bar).getByRole("link", { name: label }));
    expect(
      await screen.findByRole("heading", { name: heading }),
    ).toBeInTheDocument();
  });

  it("marks where you are", async () => {
    renderAt("/lockins");
    const bar = await screen.findByRole("navigation", { name: /main/i });
    expect(within(bar).getByRole("link", { name: "Lock-ins" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

// ---------------------------------------------------------------------------
// Where there must be nowhere else to go
// ---------------------------------------------------------------------------

describe("the nav is absent where it would do harm", () => {
  it("is hidden during the call", async () => {
    // Three minutes only works because there is nowhere else to be.
    useSpark.getState().setClientState("PENDING_ACCEPT");
    renderAt("/call");
    await screen.findByText(/ends automatically/i);
    expect(nav()).toBeNull();
  });

  it("is hidden at the consent gate", async () => {
    // A third exit turns a decision into something you can wander away from,
    // and the other person is waiting on it.
    useSpark.getState().setClientState("CALL_ENDED");
    renderAt("/call/consent");
    await screen.findByText(/would you like to connect/i);
    expect(nav()).toBeNull();
  });

  it("is hidden while an encounter is being offered", async () => {
    renderAt("/encounter");
    await screen.findByText(/you crossed paths today/i);
    expect(nav()).toBeNull();
  });

  it("is hidden on the close-out", async () => {
    renderAt("/encounter/closed");
    await screen.findByText(/that one is closed/i);
    expect(nav()).toBeNull();
  });

  it("is hidden during onboarding", async () => {
    // Onboarding now opens on the Singpass verification concept, so this waits
    // for the screen rather than for a specific line of its copy — a nav test
    // should not break when intake wording changes.
    const { container } = renderAt("/onboarding");
    await waitFor(() => expect(container.textContent).not.toBe(""));
    expect(nav()).toBeNull();
  });

  it("comes back afterwards", async () => {
    renderAt("/home");
    expect(await screen.findByRole("navigation", { name: /main/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The profile
// ---------------------------------------------------------------------------

describe("/profile", () => {
  it("offers to set one up when there is nothing yet", async () => {
    renderAt("/profile");
    expect(await screen.findByText(/you have not set this up yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /set up your profile/i }),
    ).toBeInTheDocument();
  });

  it("home says so too, while it is missing", async () => {
    // The one thing that genuinely blocks the product from working is the one
    // thing home will interrupt its own calm to mention.
    renderAt("/home");
    expect(
      await screen.findByRole("button", { name: /set up your profile/i }),
    ).toBeInTheDocument();
  });

  it("fills the home screen with the three private encounter steps", async () => {
    renderAt("/home");

    expect(
      await screen.findByRole("heading", { name: /how encounters work/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Any moment")).toBeInTheDocument();
    expect(screen.getByText("Three minutes")).toBeInTheDocument();
    expect(screen.getByText("You both choose")).toBeInTheDocument();
  });

  it("stops saying so once there is a profile", async () => {
    useSpark.getState().setChips([{ kind: "interest", label: "Coffee" }]);
    renderAt("/home");
    await screen.findByText(/one person a day/i);
    expect(screen.queryByRole("button", { name: /set up your profile/i })).toBeNull();
  });

  it("shows what onboarding captured, and lets it be changed", async () => {
    useSpark.getState().setChips([
      { kind: "intent", label: "Friends" },
      { kind: "trait", label: "Outgoing" },
      { kind: "interest", label: "Coffee" },
    ]);
    renderAt("/profile");

    expect(await screen.findByText("Coffee")).toBeInTheDocument();
    expect(screen.getByText("Outgoing")).toBeInTheDocument();
    // Intent is a choice among three, in a fixed order, nothing preselected —
    // the same rule as onboarding, because changing it must be deliberate.
    expect(
      screen.getByRole("button", { name: "Friends" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Something long term" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("changes intent by replacing it, never by accumulating", async () => {
    useSpark.getState().setChips([{ kind: "intent", label: "Friends" }]);
    renderAt("/profile");

    fireEvent.click(
      await screen.findByRole("button", { name: "Something long term" }),
    );
    await waitFor(() => {
      const intents = useSpark
        .getState()
        .chips.filter((c) => c.kind === "intent");
      expect(intents).toHaveLength(1);
      expect(intents[0].label).toBe("Something long term");
    });
  });

  it("adds and removes an interest", async () => {
    useSpark.getState().setChips([{ kind: "intent", label: "Friends" }]);
    renderAt("/profile");

    const edit = within(
      (await screen.findByText(/^interests$/i)).closest("section")!,
    ).getByRole("button", { name: /edit/i });
    fireEvent.click(edit);

    fireEvent.click(screen.getByRole("button", { name: "Climbing" }));
    await waitFor(() =>
      expect(
        useSpark.getState().chips.some((c) => c.label === "Climbing"),
      ).toBe(true),
    );

    fireEvent.click(screen.getByRole("button", { name: "Climbing" }));
    await waitFor(() =>
      expect(
        useSpark.getState().chips.some((c) => c.label === "Climbing"),
      ).toBe(false),
    );
  });

  it("adds custom characteristics and interests from Others", async () => {
    useSpark.getState().setChips([{ kind: "intent", label: "Friends" }]);
    renderAt("/profile");

    const characteristics = (
      await screen.findByText(/^characteristics$/i)
    ).closest("section")!;
    fireEvent.click(
      within(characteristics).getByRole("button", { name: /edit/i }),
    );
    fireEvent.change(
      within(characteristics).getByPlaceholderText(/add a characteristic/i),
      { target: { value: "Good listener" } },
    );
    fireEvent.click(
      within(characteristics).getByRole("button", {
        name: /add custom characteristics/i,
      }),
    );

    const interests = screen.getByText(/^interests$/i).closest("section")!;
    fireEvent.click(within(interests).getByRole("button", { name: /edit/i }));
    fireEvent.change(
      within(interests).getByPlaceholderText(/add another interest/i),
      { target: { value: "Jazz cafés" } },
    );
    fireEvent.keyDown(
      within(interests).getByPlaceholderText(/add another interest/i),
      { key: "Enter" },
    );

    await waitFor(() => {
      expect(useSpark.getState().chips).toEqual(
        expect.arrayContaining([
          { kind: "trait", label: "Good listener" },
          { kind: "interest", label: "Jazz cafés" },
        ]),
      );
    });

    fireEvent.click(
      within(interests).getByRole("button", { name: /remove jazz cafés/i }),
    );
    await waitFor(() =>
      expect(
        useSpark.getState().chips.some((chip) => chip.label === "Jazz cafés"),
      ).toBe(false),
    );
  });

  it("adds custom values and languages from Others and saves them", async () => {
    useSpark.getState().setChips([{ kind: "intent", label: "Friends" }]);
    renderAt("/profile");

    const values = (
      await screen.findByText(/^what matters to you$/i)
    ).closest("section")!;
    fireEvent.click(within(values).getByRole("button", { name: /edit/i }));
    fireEvent.change(
      within(values).getByPlaceholderText(/add another value/i),
      { target: { value: "Community" } },
    );
    fireEvent.click(
      within(values).getByRole("button", {
        name: /add custom what matters to you/i,
      }),
    );

    const languages = screen.getByText(/^languages$/i).closest("section")!;
    fireEvent.click(within(languages).getByRole("button", { name: /edit/i }));
    fireEvent.change(
      within(languages).getByPlaceholderText(/add another language/i),
      { target: { value: "Japanese" } },
    );
    fireEvent.keyDown(
      within(languages).getByPlaceholderText(/add another language/i),
      { key: "Enter" },
    );

    await waitFor(async () => {
      const profile = await adapter.getProfile();
      expect(profile.values).toContain("community");
      expect(profile.languages).toContain("japanese");
    });
  });

  it("offers a post-reveal photo but no height or appearance field", async () => {
    // INVARIANT 5. The vocabulary is the fixed list from `extract.ts`, so
    // there is nothing to type into either.
    useSpark.getState().setChips([{ kind: "interest", label: "Coffee" }]);
    const { container } = renderAt("/profile");
    await screen.findByText("Coffee");

    expect(container.querySelector('input[type="file"]')).not.toBeNull();
    expect(container.querySelector('input[type="text"]')).toBeNull();
    expect(container.querySelector("textarea")).toBeNull();
    expect(container.querySelector('input[type="range"]')).toBeNull();

    // Checked as OFFERS, not as words. The screen deliberately SAYS it has no
    // height or photo field, so scanning the prose would fail on the very
    // sentence that exists to make the promise.
    for (const control of container.querySelectorAll("button, label, input")) {
      const name = [
        control.textContent ?? "",
        control.getAttribute("aria-label") ?? "",
      ].join(" ");
      expect(name).not.toMatch(/(height|tall|body|weight)/i);
    }
  });

  it("says where the profile actually lives", async () => {
    // No auth, so there is nobody to save it to. Implying a durable account
    // would be the first lie the product told.
    //
    // The claim got STRONGER when preferences started being written through to
    // the matcher, and it has to stay honest in both directions now: the screen
    // must say that the settings do something, and must still not imply an
    // account that outlives the session.
    useSpark.getState().setChips([{ kind: "interest", label: "Coffee" }]);
    renderAt("/profile");
    expect(
      await screen.findByText(/how spark matches and plans for you/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/no sign-in yet/i)).toBeInTheDocument();
  });
});
