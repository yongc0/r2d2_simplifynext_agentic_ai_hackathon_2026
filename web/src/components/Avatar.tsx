/**
 * A generated illustration — INVARIANT 7.
 *
 * "Avatars are generated illustrations. Never a stock photo of a real person, at
 * any point, including placeholders."
 *
 * This component takes a SEED, not a URL, and draws SVG. There is no `src`, no
 * `img`, and no network request, so it cannot be pointed at a photograph even by
 * a later edit that means well — the usual failure being a placeholder service
 * dropped in "just for now" that quietly serves faces.
 *
 * It is also why the reveal reads as a person without pretending to show one.
 * The product's whole claim is that it removes judgement-by-photograph; putting
 * a face on the payoff screen would undo it at the last possible moment.
 *
 * The drawing is deterministic in the seed, so the same person looks the same on
 * every take — a re-record must match the one before it.
 */

/** FNV-1a. Small, stable, and enough to spread a word-list seed across hues. */
function hash(seed: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function Avatar({
  seed,
  size = 96,
}: {
  /** A word-list handle such as "azure-heron". Never a name. */
  seed: string;
  size?: number;
}) {
  const h = hash(seed);
  const hue = h % 360;
  // Two more hues, spaced far enough apart to stay legible after video
  // compression but inside one family, so it reads as considered rather than
  // random.
  const hueB = (hue + 40) % 360;
  const hueC = (hue + 310) % 360;

  const id = `av-${h.toString(36)}`;
  const petals = 5 + (h % 3);
  const rotation = h % 60;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      // Decorative: the name beside it is the information. A screen reader
      // announcing a procedurally generated shape helps nobody.
      aria-hidden="true"
      className="shrink-0"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={`hsl(${hue} 55% 62%)`} />
          <stop offset="100%" stopColor={`hsl(${hueB} 50% 44%)`} />
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <circle cx="50" cy="50" r="50" />
        </clipPath>
      </defs>

      <g clipPath={`url(#${id}-clip)`}>
        <rect width="100" height="100" fill={`url(#${id})`} />
        <g
          transform={`rotate(${rotation} 50 50)`}
          fill={`hsl(${hueC} 60% 78%)`}
          opacity="0.55"
        >
          {Array.from({ length: petals }, (_, i) => (
            <ellipse
              key={i}
              cx="50"
              cy="24"
              rx="9"
              ry="26"
              transform={`rotate(${(360 / petals) * i} 50 50)`}
            />
          ))}
        </g>
        <circle cx="50" cy="50" r="13" fill={`hsl(${hue} 30% 96%)`} opacity="0.9" />
      </g>
    </svg>
  );
}
