import { NavLink, useLocation } from "react-router-dom";
import { CalendarHeart, Heart, Home, Sparkles, UserRound } from "lucide-react";

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
  "/admin",            // demo operator tool, never product navigation
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
      className="absolute inset-x-0 top-0 z-30 overflow-hidden bg-cream shadow-[0_7px_20px_-14px_rgba(2,0,13,0.7)]"
    >
      <div className="flex h-14 items-center gap-2 bg-navy px-5 text-cream">
        <span className="grid size-7 place-items-center rounded-full bg-cream text-navy">
          <Heart size={15} fill="currentColor" strokeWidth={1.7} aria-hidden="true" />
        </span>
        <span className="text-[15px] font-semibold tracking-[0.02em]">Spark</span>
        <span className="ml-auto text-[9px] font-medium tracking-[0.17em] text-cream/65 uppercase">
          One real conversation
        </span>
      </div>

      <ul className="flex h-14 items-stretch justify-around border-b border-navy/10 bg-cream px-2">
        {TABS.map(({ to, label, Icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              className={({ isActive }) =>
                `relative flex h-full flex-col items-center justify-center gap-0.5 text-[9px] font-medium tracking-wide transition-colors ${
                  isActive
                    ? "text-navy after:absolute after:inset-x-5 after:bottom-0 after:h-0.5 after:rounded-full after:bg-clay"
                    : "text-navy/60 hover:text-navy"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {/* `aria-current` comes from NavLink; the icon is decorative
                      and the label is the accessible name. */}
                  <Icon size={18} strokeWidth={isActive ? 2.25 : 1.65} aria-hidden="true" />
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
export const NAV_HEIGHT_CLASS = "pt-[132px] pb-8";
