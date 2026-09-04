import { afterEach, describe, expect, it } from "vitest";

import { beginFreshProfileSession } from "../api/profile";

afterEach(() => {
  localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("fresh profile sessions", () => {
  it("starts onboarding and removes a profile left by an older build", () => {
    localStorage.setItem("spark.profile-chips.v1", "stale profile");
    window.history.replaceState({}, "", "/home?demo=1");

    beginFreshProfileSession();

    expect(window.location.pathname).toBe("/onboarding");
    expect(window.location.search).toBe("?demo=1");
    expect(localStorage.getItem("spark.profile-chips.v1")).toBeNull();
  });
});
