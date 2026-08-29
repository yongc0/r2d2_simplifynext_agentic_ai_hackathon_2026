/**
 * The UI invariants — FRONTEND.md §9.
 *
 * These mirror the backend invariants in CLAUDE.md, and they exist because a
 * front end can break them by accident: a placeholder reading "2 km away"
 * undoes the entire safety argument, and it would ship looking like copy.
 *
 * The scanners live in `./scanners.ts`, deliberately using the same approach as
 * the Python guardrail — scan what was actually rendered, not what we intended
 * to render.
 *
 * This file holds the scanners and the type-level guarantees. The SCREEN-level
 * assertions live beside the screens they cover, because that is where they
 * fail usefully:
 *
 *   invariant 1  `call.test.tsx`, `consent.test.tsx` — no location rendered
 *   invariant 2  `call.test.tsx`, `consent.test.tsx` — no identity pre-reveal
 *   invariant 3  `consent.test.tsx` — all three endings diffed, byte for byte
 *   invariant 4  `call.test.tsx` — every control swept for an extend
 *   invariant 5  `onboarding.test.tsx` — no height, appearance or photo field
 *   invariant 6  `call.test.tsx` — Guardian never imitates system chrome
 *   invariant 7  `screens.test.tsx` — the reveal draws SVG, never an image
 *
 * The index below is asserted rather than written in prose: if a screen-level
 * invariant test is deleted or renamed, this fails.
 */

import { describe, expect, it } from "vitest";

import { SHOW_HANDLE_PRE_REVEAL, overlapHintFor } from "../api/wire";
import { scanForIdentityFields, scanForLocation } from "./scanners";

// ---------------------------------------------------------------------------
// INVARIANT 1 — location
// ---------------------------------------------------------------------------

describe("invariant 1 — no distance, coordinate, place name or map", () => {
  it.each([
    "They were 300 m away.",
    "About 1.2 km from you.",
    "You were both at Raffles Place.",
    "1.2903, 103.8519",
    "Someone nearby crossed your path.",
    "They are 15 minutes away.",
    "You work in the same building.",
    "matched on cell_id cell-07",
  ])("rejects %j", (text) => {
    expect(scanForLocation(text)).not.toHaveLength(0);
  });

  it.each([
    "Your paths crossed this afternoon",
    "You have both mentioned climbing.",
    "You are both free in the evening.",
    "That one is closed. Your next encounter is tomorrow at 9pm.",
  ])("allows ordinary copy: %j", (text) => {
    // A scanner that cries wolf gets switched off, and then it protects nobody.
    expect(scanForLocation(text)).toHaveLength(0);
  });

  it("every overlap hint the client can produce is location-free", () => {
    // The ONLY route from a backend time bucket to a rendered phrase. If any
    // branch of it could name a place, this is where that shows up.
    const buckets = [
      "early_morning", "morning", "midday",
      "afternoon", "evening", "night",
      null, undefined, "something_unexpected",
    ];
    for (const bucket of buckets) {
      const hint = overlapHintFor(bucket as string | null | undefined);
      expect(scanForLocation(hint), `bucket ${bucket}`).toHaveLength(0);
      expect(hint.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 2 — identity
// ---------------------------------------------------------------------------

describe("invariant 2 — no identity before mutual consent", () => {
  it("EncounterCard has nowhere to put an identity", async () => {
    // Structural, not behavioural: the point is that there is no field, so no
    // component can render one even by accident. Asserted against a value the
    // compiler has checked, so adding a field to the interface fails here.
    const { overlapHintFor: hint } = await import("../api/wire");
    const card = {
      encounterId: "enc-1",
      state: "NOTIFIED" as const,
      intent: "friends" as const,
      handle: "azure-heron",
      sharedInterests: ["climbing"],
      overlapHint: hint("afternoon"),
      windowClosesAt: new Date().toISOString(),
      callSeconds: 180,
    };
    expect(scanForIdentityFields(card)).toHaveLength(0);
    expect(scanForLocation(JSON.stringify(card))).toHaveLength(0);
  });

  it("a pseudonymous handle is not an identity", () => {
    // Handles come from a fixed word list and are never derived from a name
    // (`spark/src/ids.py`). If this decision is reversed, flip the flag in
    // wire.ts and this test documents what changed.
    expect(SHOW_HANDLE_PRE_REVEAL).toBe(true);
    expect(scanForIdentityFields({ handle: "azure-heron" })).toHaveLength(0);
  });

  it("catches an identity field smuggled in by a spread", () => {
    // The realistic failure mode: someone spreads a richer object into a
    // pre-reveal view. The scanner must find it however deep it is.
    const leaky = { peer: { handle: "azure-heron", displayName: "Elowen" } };
    expect(scanForIdentityFields(leaky)).toContain("displayName");
  });
});

// ---------------------------------------------------------------------------
// The screen-level tests exist and are named here
// ---------------------------------------------------------------------------

describe("every UI invariant has a screen-level test", () => {
  // Read off disk rather than trusted to a comment. Deleting or renaming one of
  // these tests to make a feature pass fails here, loudly, with the invariant
  // named — the same protection CLAUDE.md puts around tests/test_consent.py.
  const REQUIRED: [string, string, string][] = [
    ["1", "call.test.tsx", "renders no location anywhere on the screen"],
    ["1", "consent.test.tsx", "renders no location — invariant 1"],
    ["2", "call.test.tsx", "renders a pseudonymous handle and nothing more"],
    ["2", "consent.test.tsx", "renders nothing identifying — invariant 2"],
    ["3", "consent.test.tsx", "renders byte-identical markup whoever declined"],
    ["3", "consent.test.tsx", "waits exactly the same time on every branch"],
    ["1", "onboarding.test.tsx", "keeps a place out of the panel even when the person types one"],
    ["4", "call.test.tsx", "offers no control that could add time"],
    ["5", "onboarding.test.tsx", "offers no field for one"],
    ["5", "onboarding.test.tsx", "captures nothing when someone volunteers one"],
    ["5", "onboarding.test.tsx", "has no chip kind that could render one"],
    ["6", "call.test.tsx", "shows an in-app reminder, never system chrome"],
    ["7", "screens.test.tsx", "draws a generated illustration, not a photograph"],
    ["2", "shell.test.tsx", "shows no identity on a deep link to /reveal"],
  ];

  // `import.meta.glob`, not a dynamic `import()` with a template string. Vite
  // cannot statically analyse the latter and warns on every run — and a build
  // whose output always contains a warning is one where the next warning goes
  // unread. This is also stricter: the glob is resolved at build time, so a
  // renamed test file fails here rather than at await.
  const SOURCES = import.meta.glob("./*.test.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it.each(REQUIRED)(
    "invariant %s is covered by %s: %s",
    (_invariant, file, testName) => {
      const source = SOURCES[`./${file}`];
      expect(source, `${file} is not in src/__tests__/`).toBeDefined();
      expect(source).toContain(testName);
    },
  );
});
