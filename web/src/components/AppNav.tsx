import { NavLink, useLocation } from "react-router-dom";
import { CalendarHeart, Home, Sparkles, UserRound } from "lucide-react";

/**
 * The app's navigation — FRONTEND.md §5.2, amended.
 *
 * WHY THIS EXISTS, GIVEN §5.2 SAYS "NO PROFILES"
 *
 * That rule is about not BROWSING OTHER PEOPLE, which is the product argument:
 * there is no feed, no discovery, no scrolling through strangers. Reaching your
 * own lock-ins, your own plans and your own profile does not touch it. A
 * Discover tab would; these four do not, and there will not be a fifth that
 * lists people you have not met.
 *
 * WHERE IT IS DELIBERATELY ABSENT
 *
 * Not during the call, the consent gate, the reveal, or an encounter that is
 * being offered. Two reasons, and the second matters more:
 *
 *   A nav bar during three minutes is an escape hatch, and the format only
 *   works because there is nowhere else to be.
 *
 *   A nav bar during the consent gate is a way to avoid answering. The gate is
 *   two buttons and a genuinely uncertain wait; adding a third exit turns a
 *   decision into a thing you can wander away from, and the other person is
 *   waiting on it.
 *
 * `HIDDEN_ON` is a prefix list rather than a set, so a nested route added later
 * under `/call` inherits the rule instead of quietly escaping it.
 */

/** Route prefixes where the app must offer nowhere else to go. */
const HIDDEN_ON = [
  "/onboarding",       // finish setting up, or do not
  "/encounter",        // includes /waiting and /closed
  "/call",             // includes /call/consent
  "/reveal",           // one action: add to lock-ins
];

const TABS = [
  { to: "/home", label: "Home", Icon: Home },
  { to: "/plans", label: "Plans", Icon: CalendarHeart },
  { to: "/lockins", label: "Lock-ins", Icon: Sparkles },
  { to: "/profile", label: "You", Icon: UserRound },
];

export function useNavVisible(): boolean {
  const { pathname } = useLocation();
  return !HIDDEN_ON.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function AppNav() {
  const visible = useNavVisible();
  if (!visible) return null;

  return (
    <nav
      aria-label="Main"
      className="absolute inset-x-0 bottom-0 z-30 border-t border-white/[0.07] bg-bg/95 px-2 pt-2 pb-3 backdrop-blur"
    >
      <ul className="flex items-stretch justify-around">
        {TABS.map(({ to, label, Icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              className={({ isActive }) =>
                `flex flex-col items-center gap-1 rounded-xl py-1.5 text-[10px] transition-colors ${
                  isActive
                    ? "text-accent-soft"
                    : "text-muted hover:text-text"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {/* `aria-current` comes from NavLink; the icon is decorative
                      and the label is the accessible name. */}
                  <Icon size={19} strokeWidth={isActive ? 2.2 : 1.7} aria-hidden="true" />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * How much room the nav takes, so a screen can reserve it.
 *
 * A constant rather than a magic number repeated in four files: the bar is
 * absolutely positioned, and a screen that forgets this has its last row of
 * content sitting underneath it — which on a phone frame is invisible until
 * somebody scrolls, and on camera is never.
 */
export const NAV_HEIGHT_CLASS = "pb-24";
