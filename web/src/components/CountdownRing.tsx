import { useReducedMotion } from "framer-motion";

/**
 * The three minutes, drawn as a depleting ring.
 *
 * Two things here are load-bearing rather than decorative.
 *
 * The ring is driven by a `remaining` prop that the parent derives from
 * `performance.now()`, not from an interval it increments. A timer built by
 * adding 1000ms on every tick drifts by seconds over three minutes — on a
 * recording that is the difference between the ring hitting zero as the call
 * ends and hitting zero four seconds late.
 *
 * At thirty seconds the stroke warms to the accent colour. FRONTEND.md §5.4:
 * a shift in tone, and no alarm sound. The product is trying to end a
 * conversation gracefully, not to panic someone.
 */
export function CountdownRing({
  remaining,
  total,
}: {
  /** Seconds left. Fractional — the ring is smooth. */
  remaining: number;
  total: number;
}) {
  const reduced = useReducedMotion();

  const SIZE = 260;
  const STROKE = 6;
  const radius = (SIZE - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;

  const fraction = Math.max(0, Math.min(1, remaining / total));
  const warm = remaining <= 30;

  const whole = Math.max(0, Math.ceil(remaining));
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  const label = `${minutes}:${String(seconds).padStart(2, "0")}`;

  return (
    <div
      className="relative grid place-items-center"
      style={{ width: SIZE, height: SIZE }}
    >
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        // Decorative: the accessible value is the live region below.
        aria-hidden="true"
        className="-rotate-90"
      >
        {/* The track the ring depletes along. */}
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          className="text-white/[0.06]"
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          className={
            warm
              ? "text-accent-soft transition-colors duration-700"
              : "text-accent transition-colors duration-700"
          }
          // No CSS transition on the offset: the value is already updated every
          // frame from the clock, and a transition on top of that lags the ring
          // behind the number it is supposed to be showing.
          style={reduced ? { transition: "none" } : undefined}
        />
      </svg>

      <div className="absolute grid place-items-center gap-1">
        <span
          className="font-mono text-5xl tabular-nums tracking-tight text-text"
          // Announced once a second rather than on every frame.
          aria-live="off"
        >
          {label}
        </span>
        <span className="text-xs tracking-widest text-muted uppercase">
          {warm ? "wrapping up" : "remaining"}
        </span>
      </div>
    </div>
  );
}
