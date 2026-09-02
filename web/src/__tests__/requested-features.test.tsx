import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { moderateMessage } from "../screens/Chat";
import Chat from "../screens/Chat";
import SharedDateIdeas from "../screens/SharedDateIdeas";
import Home from "../screens/Home";
import { SingpassVerification } from "../components/SingpassVerification";
import { useSpark } from "../store/useSpark";
import { MockAdapter } from "../api/mock";
import { setAdapter } from "../api/adapter";

const lockIn = {
  lockInId: "lock-test",
  person: {
    personId: "peer-test",
    displayName: "Avery",
    avatarSeed: "avery",
    sharedInterests: ["coffee"],
  },
  openedAt: "2026-09-01T00:00:00.000Z",
  lastContactAt: null,
  state: "active" as const,
};

beforeEach(() => useSpark.getState().reset());

describe("requested profile and communication features", () => {
  it("offers a dedicated foreigner signup path", () => {
    render(<SingpassVerification onComplete={() => {}} onForeigner={() => {}} />);
    expect(screen.getByRole("button", { name: /sign up as a foreigner/i })).toBeVisible();
  });

  it("masks profanity and potentially harmful words", () => {
    expect(moderateMessage("I hate this shit")).toEqual({
      text: "I •••• this ••••",
      moderated: true,
    });
  });

  it("lets a lock-in send a moderated chat message and offers every attachment type", () => {
    useSpark.getState().setLockIns([lockIn]);
    render(
      <MemoryRouter initialEntries={["/lockins/lock-test/chat"]}>
        <Routes>
          <Route path="/lockins/:lockInId/chat" element={<Chat />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "Photo" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Voice" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Document" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "This is shit" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(screen.getByText("This is ••••")).toBeVisible();
    expect(screen.getByText(/some language was masked/i)).toBeVisible();
  });

  it("shows shared likes and supports invite acceptance", () => {
    useSpark.getState().setLockIns([lockIn]);
    useSpark.getState().proposeDateIdea({
      lockInId: lockIn.lockInId,
      title: "Coffee and a gallery",
      detail: "Saturday · 90 minutes",
      proposedBy: "you",
    });
    render(
      <MemoryRouter>
        <SharedDateIdeas />
      </MemoryRouter>,
    );

    const card = screen.getByRole("heading", { name: "Coffee and a gallery" }).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: /avery likes/i }));
    expect(within(card).getByText("BOTH LIKE")).toBeVisible();
    fireEvent.click(within(card).getByRole("button", { name: /send an invite/i }));
    fireEvent.click(within(card).getByRole("button", { name: "Accept" }));
    expect(within(card).getByText("Invite accepted")).toBeVisible();
  });

  it("shows every lock-in in the Home chat list without timer copy", async () => {
    const adapter = new MockAdapter();
    adapter.getLockIns = async () => [lockIn];
    setAdapter(adapter);
    useSpark.getState().setLockIns([lockIn]);
    useSpark.getState().sendChatMessage(lockIn.lockInId, {
      from: "them",
      text: "Are we still on for coffee?",
    });
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Home />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Chats" })).toBeVisible();
    expect(screen.getByRole("button", { name: /Avery/ })).toHaveTextContent("Are we still on for coffee?");
    expect(screen.queryByText("There is no timer to watch.")).toBeNull();
  });
});
