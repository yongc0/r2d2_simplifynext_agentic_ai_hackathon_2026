import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { setAdapter } from "../api/adapter";
import { MockAdapter } from "../api/mock";
import { useSpark } from "../store/useSpark";

function renderAt(path: string) {
  // Demo mode deliberately reads the real browser query string once at mount,
  // so the test URL must match the in-memory router's URL.
  window.history.replaceState({}, "", path);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  localStorage.clear();
  const adapter = new MockAdapter();
  await adapter.reset(42);
  setAdapter(adapter);
  useSpark.getState().reset();
});

afterEach(() => setAdapter(null));

describe("demo Profile Lab", () => {
  it("is unavailable unless demo mode was explicitly requested", async () => {
    renderAt("/admin/profiles");
    expect(await screen.findByText(/one person a day/i)).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Profile Lab" })).toBeNull();
  });

  it("creates a browser-local synthetic profile and activates it", async () => {
    renderAt("/admin/profiles?demo=1");
    expect(await screen.findByRole("heading", { name: "Profile Lab" })).toBeVisible();
    expect(screen.getByText(/not an authenticated admin system/i)).toBeVisible();

    const editor = screen.getByRole("heading", { name: "Create test profile" }).closest("section")!;
    fireEvent.change(within(editor).getByLabelText("Preset name"), {
      target: { value: "Weekend tester" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Outgoing" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Coffee" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Honesty" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Night" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Save test profile" }));

    expect(screen.getByRole("heading", { name: "Weekend tester" })).toBeVisible();
    expect(localStorage.getItem("spark.demo.test-profiles.v1")).toContain("Weekend tester");

    fireEvent.click(screen.getByRole("button", { name: "Use Weekend tester" }));

    expect(await screen.findByText(/what spark uses to find someone/i)).toBeVisible();
    expect(screen.getByText("Outgoing")).toBeVisible();
    expect(screen.getByText("Coffee")).toBeVisible();
    expect(screen.getByText("Honesty")).toBeVisible();
    expect(screen.getByRole("button", { name: "Friends" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await waitFor(() =>
      expect(useSpark.getState().chips.some((chip) => chip.label === "Night")).toBe(true),
    );
  });

  it("removes a saved synthetic profile", async () => {
    renderAt("/admin/profiles?demo=1");
    expect(await screen.findByRole("heading", { name: "Curious regular" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Remove Curious regular" }));

    expect(screen.queryByRole("heading", { name: "Curious regular" })).toBeNull();
  });
});
