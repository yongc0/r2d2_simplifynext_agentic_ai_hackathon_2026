import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ItineraryView } from "../components/ItineraryView";
import { ReflectionForm } from "../components/ReflectionForm";
import { RouteMap } from "../components/RouteMap";
import type { Itinerary, ItineraryStop } from "../api/types";

/**
 * The date planner's UI invariants.
 *
 * Three of these are about not lying to somebody who is about to leave the
 * house: a venue whose hours nobody recorded must not read as open, a travel
 * estimate must not read as measured, and a directions link must not carry a
 * credential. The rest are the privacy promise the reflection form makes.
 */

function stop(over: Partial<ItineraryStop> = {}): ItineraryStop {
  return {
    stopId: "s1",
    order: 1,
    activityType: "activity",
    venueId: "v1",
    venueName: "The Gallery",
    address: "1 Somewhere Road",
    lat: 1.3,
    lon: 103.8,
    startTime: "18:00",
    endTime: "19:15",
    durationMinutes: 75,
    estimatedCost: "Free",
    costBand: "free",
    rationale: "You have both mentioned photography.",
    travelFromPrevious: null,
    mapsUrl:
      "https://www.google.com/maps/dir/?api=1&destination=1.3,103.8&travelmode=walking",
    openingState: "open",
    openingHours: "Mo-Su 10:00-19:00",
    openingDetail: "",
    isCommercialPartner: false,
    ...over,
  };
}

function itinerary(stops: ItineraryStop[]): Itinerary {
  return {
    itineraryId: "itin-1",
    lockInId: "lock-1",
    pathId: "p-1",
    headline: "A gallery, then somewhere to eat",
    timeBucket: "evening",
    dayLabel: "An evening",
    stops,
    totalDurationMinutes: 150,
    totalCostEstimate: "Roughly $10-20 each",
    groundedIn: ["photography"],
    status: "draft",
    note: "",
    attribution: "© OpenStreetMap contributors",
    updatedAt: new Date().toISOString(),
    hasReflection: false,
  };
}

const renderIt = (node: React.ReactNode) =>
  render(<MemoryRouter>{node}</MemoryRouter>);

describe("an itinerary", () => {
  it("never renders unknown opening hours as open", async () => {
    renderIt(
      <ItineraryView
        itinerary={itinerary([stop({ openingState: "unknown", openingHours: null })])}
      />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    // The honest sentence, and NOT the confident one.
    expect(
      await screen.findByText(/opening hours are not recorded/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^open then/i)).toBeNull();
  });

  it("says a travel time is an estimate", async () => {
    const second = stop({
      stopId: "s2",
      order: 2,
      venueName: "The Kitchen",
      activityType: "food",
      startTime: "19:23",
      endTime: "20:23",
      durationMinutes: 60,
      travelFromPrevious: {
        minutes: 8,
        metres: 620,
        mode: "walking",
        estimated: true,
        detail: "Straight-line estimate, not a routed journey.",
      },
    });
    renderIt(<ItineraryView itinerary={itinerary([stop(), second])} />);

    expect(await screen.findByText(/8 min walking/i)).toBeInTheDocument();
    expect(screen.getByText(/\(estimated\)/i)).toBeInTheDocument();
  });

  it("offers directions through a link that carries no credential", async () => {
    renderIt(<ItineraryView itinerary={itinerary([stop()])} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));

    const link = await screen.findByRole("link", { name: /navigate/i });
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("google.com/maps/dir/");
    expect(href).toContain("destination=1.3,103.8");
    // No key, token or signature may ever reach the bundle.
    expect(href).not.toMatch(/[?&](key|token|signature|api_key)=/i);
  });

  it("shows an address only when there is one", async () => {
    renderIt(<ItineraryView itinerary={itinerary([stop({ address: null })])} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    // Never a guess assembled from the surrounding streets.
    expect(await screen.findByText(/address not listed/i)).toBeInTheDocument();
  });

  it("credits OpenStreetMap wherever the venues are shown", () => {
    renderIt(<ItineraryView itinerary={itinerary([stop()])} />);
    expect(screen.getByText(/OpenStreetMap contributors/i)).toBeInTheDocument();
  });
});

describe("the route map", () => {
  it("numbers its markers in itinerary order", () => {
    const stops = [
      stop(),
      stop({ stopId: "s2", order: 2, venueName: "The Kitchen", lat: 1.31, lon: 103.81 }),
    ];
    render(
      <RouteMap stops={stops} attribution="© OpenStreetMap contributors" />,
    );
    const image = screen.getByRole("img");
    // The accessible name carries the order, so the map is not information
    // available only to people who can see it.
    expect(image.getAttribute("aria-label")).toMatch(/1, The Gallery/);
    expect(image.getAttribute("aria-label")).toMatch(/2, The Kitchen/);
  });

  it("does not fetch a map tile from anywhere", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(
      <RouteMap stops={[stop()]} attribution="© OpenStreetMap contributors" />,
    );
    // The whole reason the map is drawn rather than tiled: everything else in
    // this client works offline, and a map that goes grey on the one screen the
    // feature is about would undo that.
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("the post-date form", () => {
  it("states the privacy promise before anything is answered", () => {
    renderIt(<ReflectionForm itineraryId="itin-1" />);
    expect(
      screen.getByText(/never shown to the person you met/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/never told whether you filled it in/i),
    ).toBeInTheDocument();
  });

  it("says plainly that a 'no' does not travel", () => {
    renderIt(<ReflectionForm itineraryId="itin-1" />);
    expect(
      screen.getByText(/nobody is told this/i),
    ).toBeInTheDocument();
  });

  it("needs only an overall rating and an answer, not every aspect", async () => {
    renderIt(<ReflectionForm itineraryId="itin-1" />);
    const save = screen.getByRole("button", { name: /save/i });
    expect(save).toBeDisabled();

    fireEvent.click(
      screen.getAllByRole("radio", { name: /4 out of 5/i })[0],
    );
    fireEvent.click(screen.getByRole("button", { name: "Maybe" }));
    await waitFor(() => expect(save).toBeEnabled());
  });

  it("offers no way to tell the other person anything", () => {
    renderIt(<ReflectionForm itineraryId="itin-1" />);
    // No share, no send, no "let them know" — the form has exactly one
    // destination and it is the author's own record.
    expect(screen.queryByRole("button", { name: /share|send|tell them/i })).toBeNull();
  });
});
