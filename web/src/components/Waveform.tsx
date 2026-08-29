import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * The thing that makes the screen read as a live call.
 *
 * A bar-per-column waveform on canvas, fed an amplitude every frame. Canvas
 * rather than 40 animated DOM nodes: this runs for three unbroken minutes while
 * a screen recorder is also running, and dropped frames are visible in the
 * final video in a way they never are in a browser.
 *
 * The amplitude comes in through a ref rather than a prop. A prop would rerender
 * this component sixty times a second and take the whole screen with it; the ref
 * lets the parent update a number while React does nothing at all.
 *
 * Under `prefers-reduced-motion` it renders a static level and stops — §7 says
 * respect it, and a moving waveform is exactly the kind of thing it is for.
 */
export function Waveform({
  amplitudeRef,
  speakerRef,
  bars = 44,
}: {
  amplitudeRef: React.MutableRefObject<number>;
  speakerRef: React.MutableRefObject<"local" | "remote" | "silence">;
  bars?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Backing store at device resolution, so the bars are crisp when the
    // recording is scaled to 1080p.
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssWidth = canvas.clientWidth;
    const cssHeight = canvas.clientHeight;
    canvas.width = Math.floor(cssWidth * dpr);
    canvas.height = Math.floor(cssHeight * dpr);
    ctx.scale(dpr, dpr);

    // A short history so the bars scroll rather than all pulsing together —
    // one shared value across every bar looks like a graphic equaliser preset.
    const history: number[] = new Array(bars).fill(0.05);
    let frame = 0;
    let raf = 0;

    const ACCENT = "#B03060";
    const ACCENT_SOFT = "#E8A0B8";
    const IDLE = "#3A3134";

    const draw = () => {
      const amplitude = amplitudeRef.current;
      const speaker = speakerRef.current;

      // Push one sample per frame, oldest out.
      history.push(amplitude);
      history.shift();

      ctx.clearRect(0, 0, cssWidth, cssHeight);

      const gap = 3;
      const barWidth = (cssWidth - gap * (bars - 1)) / bars;
      const mid = cssHeight / 2;

      for (let i = 0; i < bars; i++) {
        const value = history[i];
        // Taper the ends so the waveform sits in the frame rather than being
        // chopped off by it.
        const taper = Math.sin((i / (bars - 1)) * Math.PI) ** 0.6;
        const height = Math.max(2, value * taper * cssHeight * 0.82);
        const x = i * (barWidth + gap);

        ctx.fillStyle =
          speaker === "silence"
            ? IDLE
            : speaker === "remote"
              ? ACCENT_SOFT
              : ACCENT;
        // Rounded caps: a rectangle reads as a chart, a pill reads as audio.
        ctx.beginPath();
        ctx.roundRect(x, mid - height / 2, barWidth, height, barWidth / 2);
        ctx.fill();
      }

      frame++;
      raf = requestAnimationFrame(draw);
    };

    if (reduced) {
      // One static frame at a resting level. No animation loop at all.
      history.fill(0.18);
      draw();
      cancelAnimationFrame(raf);
      return;
    }

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [amplitudeRef, speakerRef, bars, reduced]);

  return (
    <canvas
      ref={canvasRef}
      className="h-20 w-full"
      // Decorative. The call's state is announced by the screen around it.
      aria-hidden="true"
    />
  );
}
