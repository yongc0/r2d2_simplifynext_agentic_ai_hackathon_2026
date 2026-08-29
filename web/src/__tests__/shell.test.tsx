/**
 * The shell — milestone 1's acceptance test.
 *
 * Every route mounts, the device frame wraps it, and the store starts in a
 * known state. Cheap, and it catches the one failure that would be worst to
 * find during a recording: the app crashing on mount.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { useSpark } from "../store/useSpark";

/** No route shows a milestone stub any more. Kept as an empty list rather than
 *  deleted, so the next screen added has somewhere obvious to be listed while
 *  it is still a placeholder — and so this file keeps saying, out loud, that
 *  there are none. */
const STUB_ROUTES: string[] = [];

/** Routes with a real screen, and a string that proves it rendered.
 *
 *  `/call` and `/call/consent` are deliberately absent: they are GUARDED, and
 *  mounting them from a fresh store is exactly what must not work. They have
 *  their own tests below, on both sides of the guard. */
const BUILT_ROUTES: [string, RegExp][] = [
  ["/onboarding", /start as a verified person/i],
  ["/home", /one person a day/i],
  ["/lockins", /five at a time, so each one gets your attention/i],

  ["/encounter", /you crossed paths today/i],
  ["/encounter/waiting", /waiting for the other person/i],

  ["/encounter/closed", /that one is closed/i],
];

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

describe("shell", () => {
  beforeEach(() => useSpark.getState().reset());

  it.skipIf(STUB_ROUTES.length === 0).each(STUB_ROUTES)("mounts %s", (path) => {
    renderAt(path);
    expect(screen.getByText(path)).toBeInTheDocument();
  });

  it.each(BUILT_ROUTES)("mounts %s (built)", async (path, marker) => {
    renderAt(path);
    expect(await screen.findByText(marker)).toBeInTheDocument();
  });

  it("sends an unknown route home rather than to a 404", async () => {
    renderAt("/does-not-exist");
    // Awaited: `/home` fetches its lock-in list, and asserting before that
    // settles leaves a state update landing outside the test.
    expect(await screen.findByText(/one person a day/i)).toBeInTheDocument();
  });

  it("shows no identity on a deep link to /reveal", async () => {
    // INVARIANT 2. `/reveal` is not addressable: it renders from the store,
    // there is no id in the URL to fetch with, and an empty store means there
    // was no mutual yes in this session. Typing the URL, or pressing back after
    // a close-out, must land somewhere true rather than on a broken screen.
    renderAt("/reveal");
    expect(await screen.findByText(/one person a day/i)).toBeInTheDocument();
  });

  it("hides the demo strip unless it was asked for", async () => {
    // §8 is an operator's tool. It is behind `?demo=1`, and these tests render
    // without one, so nothing of it may be on screen.
    const { container } = renderAt("/home");
    await screen.findByText(/one person a day/i);
    expect(container.textContent ?? "").not.toMatch(/skip to encounter window/i);
  });

  it("sends / home", async () => {
    renderAt("/");
    expect(await screen.findByText(/one person a day/i)).toBeInTheDocument();
  });
});

describe("store", () => {
  beforeEach(() => useSpark.getState().reset());

  it("starts with no encounter and no identity", () => {
    const s = useSpark.getState();
    expect(s.clientState).toBe("IDLE");
    expect(s.card).toBeNull();
    expect(s.revealed).toBeNull();
    expect(s.consentOutcome).toBeNull();
  });

  it("reset is deterministic but keeps the operator's panel open", () => {
    // §8: takes are repeatable. Re-opening the Director panel between every
    // take is exactly the friction the demo controls exist to remove.
    const { toggleDirector, setRevealed, reset } = useSpark.getState();
    toggleDirector();
    setRevealed({
      personId: "p1",
      displayName: "Elowen Brackley",
      avatarSeed: "seed",
      sharedInterests: ["climbing"],
    });
    reset(99);

    const s = useSpark.getState();
    expect(s.revealed).toBeNull();
    expect(s.seed).toBe(99);
    expect(s.directorOpen).toBe(true);
  });

  it("bounds the event log so a long take does not grow without limit", () => {
    const { pushEvent } = useSpark.getState();
    for (let i = 0; i < 250; i++) {
      pushEvent({
        ts: new Date().toISOString(),
        agent: "match",
        action: "selected candidate",
        detail: `#${i}`,
        durationMs: 12,
        status: "ok",
      });
    }
    expect(useSpark.getState().events).toHaveLength(200);
  });
});

// ---------------------------------------------------------------------------
// Route guards — a URL is not a state machine
// ---------------------------------------------------------------------------

describe("direct links cannot skip the encounter", () => {
  // Typing `/call/consent` on a fresh store and pressing Yes used to reach the
  // reveal with the scripted identity: no encounter accepted, no call, no gate.
  // The backend's gate ordering was fixed first; this is the same defect on the
  // client, where the only "gate" was the order screens happened to be visited.

  it.each([
    ["/call", /one person a day/i],
    ["/call/consent", /one person a day/i],
    ["/reveal", /one person a day/i],
  ])("sends %s home from a fresh store", async (path, marker) => {
    renderAt(path);
    expect(await screen.findByText(marker)).toBeInTheDocument();
  });

  it("shows no consent question on a direct link", async () => {
    renderAt("/call/consent");
    await screen.findByText(/one person a day/i);
    expect(screen.queryByText(/would you like to connect/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^yes$/i })).toBeNull();
  });

  it("shows no call on a direct link", async () => {
    renderAt("/call");
    await screen.findByText(/one person a day/i);
    expect(screen.queryByText(/ends automatically/i)).toBeNull();
  });

  it("returns a mid-call viewer to the call, not to home", async () => {
    // Sending someone home would end an encounter that is still running, so
    // the fallback depends on where they actually are.
    useSpark.getState().setClientState("CONNECTED");
    renderAt("/call/consent");
    expect(await screen.findByText(/ends automatically/i)).toBeInTheDocument();
  });

  it("admits the call once an encounter has been accepted", async () => {
    useSpark.getState().setClientState("PENDING_ACCEPT");
    renderAt("/call");
    expect(await screen.findByText(/ends automatically/i)).toBeInTheDocument();
  });

  it("admits the gate once the call has ended", async () => {
    useSpark.getState().setClientState("CALL_ENDED");
    renderAt("/call/consent");
    expect(await screen.findByText(/would you like to connect/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// A decline must not leave the client eligible for the call it refused
// ---------------------------------------------------------------------------

/**
 * A real in-router navigation, triggered after the fact.
 *
 * Rendering the app at a URL is not the same as NAVIGATING to it: the store
 * carries state across a client-side navigation, and that state is what the
 * guards read. This renders beside the app inside the same router so the
 * navigation is the genuine article.
 */
function GoTo({ to }: { to: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to)}>
      {`go to ${to}`}
    </button>
  );
}

function renderWithNavigation(from: string) {
  return render(
    <MemoryRouter
      initialEntries={[from]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
      <GoTo to="/call" />
      <GoTo to="/call/consent" />
      <GoTo to="/reveal" />
    </MemoryRouter>,
  );
}

describe("declining an encounter", () => {
  // Both answers used to set PENDING_ACCEPT before navigating, and the `/call`
  // guard admits that state — so "Not tonight" left the client still eligible
  // to walk into the call it had just refused. The guard was working; it was
  // being told the wrong thing.

  it("cannot walk into the call it just refused", async () => {
    renderWithNavigation("/encounter");

    fireEvent.click(await screen.findByRole("button", { name: /not tonight/i }));

    // The close-out, first — the same one every non-connection reaches.
    expect(await screen.findByText(/that one is closed/i)).toBeInTheDocument();

    // Now try to get into the call anyway.
    fireEvent.click(screen.getByRole("button", { name: "go to /call" }));
    await waitFor(() =>
      expect(screen.getByText(/one person a day/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/ends automatically/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /end call/i })).toBeNull();

    // And the gate beyond it stays shut too.
    fireEvent.click(screen.getByRole("button", { name: "go to /call/consent" }));
    await waitFor(() =>
      expect(screen.getByText(/one person a day/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/would you like to connect/i)).toBeNull();

    // And so does the reveal.
    fireEvent.click(screen.getByRole("button", { name: "go to /reveal" }));
    await waitFor(() =>
      expect(screen.getByText(/one person a day/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/you both said yes/i)).toBeNull();
    expect(useSpark.getState().revealed).toBeNull();
  });

  it("leaves the encounter abandoned, not pending", async () => {
    // The state is the thing the guards read, so it is asserted directly as
    // well as through its consequences.
    renderWithNavigation("/encounter");
    fireEvent.click(await screen.findByRole("button", { name: /not tonight/i }));
    await screen.findByText(/that one is closed/i);

    expect(useSpark.getState().clientState).toBe("ABANDONED");
  });

  it("still admits the call after an accept", async () => {
    // The other half: the fix must not make accepting stop working.
    renderWithNavigation("/encounter");
    fireEvent.click(await screen.findByRole("button", { name: /^accept$/i }));

    await waitFor(() =>
      expect(useSpark.getState().clientState).toBe("PENDING_ACCEPT"),
    );
    fireEvent.click(screen.getByRole("button", { name: "go to /call" }));
    expect(await screen.findByText(/ends automatically/i)).toBeInTheDocument();
  });
});
