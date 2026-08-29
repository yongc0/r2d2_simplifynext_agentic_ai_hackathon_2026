import "@testing-library/jest-dom/vitest";

/**
 * jsdom does not implement `<canvas>`.
 *
 * `Waveform` asks for a 2D context on mount and draws to it every frame. None
 * of that drawing is under test — the waveform is a picture, and the properties
 * that matter (the hard stop, the absence of an extend, what the screen says)
 * are asserted from the DOM.
 *
 * Without this stub, jsdom prints a "Not implemented" stack for every test that
 * mounts the call screen. That noise is worse than harmless: a suite whose
 * output is always full of red is a suite nobody reads, and the release gate in
 * DEPLOYMENT_READINESS.md is only meaningful if a clean run looks clean.
 *
 * A Proxy rather than a hand-written fake, so adding a drawing call to
 * `Waveform` later does not reintroduce the noise.
 */
const noopContext = new Proxy(
  {},
  {
    get: (_target, property) => {
      // Canvas state properties (fillStyle, lineWidth, ...) are read back as
      // well as written, so return a benign value rather than a function for
      // anything that is not obviously a method call.
      if (property === "canvas") return undefined;
      return () => undefined;
    },
    set: () => true,
  },
);

HTMLCanvasElement.prototype.getContext = (() =>
  noopContext) as unknown as HTMLCanvasElement["getContext"];
