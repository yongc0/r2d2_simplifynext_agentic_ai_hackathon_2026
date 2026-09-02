import { useEffect } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";

import { Avatar } from "../components/Avatar";
import { useSpark } from "../store/useSpark";

/**
 * /reveal — identity, after a mutual yes (FRONTEND.md §5.6).
 *
 * The only screen in the app permitted to render a name.
 *
 * IT READS FROM `store.revealed` AND NOWHERE ELSE. That field is set in exactly
 * one place — the `outcome === "mutual"` branch in `Consent.tsx`, from the
 * adapter's response — and on the Python side `build_reveal` is the sole
 * constructor of an identity-bearing view and refuses without a mutual yes.
 * So this screen cannot show a name that two people did not both agree to.
 *
 * A DEEP LINK HERE SHOWS NOTHING. `/reveal` typed into the address bar, or
 * reached by a back button after a close-out, finds an empty store and
 * redirects. It does not fetch, and there is no id in the URL it could fetch
 * with — the reveal is not addressable, which is the point.
 *
 * INVARIANT 7: the illustration is generated from `avatarSeed`. `Avatar` takes
 * a seed rather than a URL and draws SVG, so no photograph can appear here.
 *
 * The animation is a fade and a rise, per §7. Not confetti — two people agreeing
 * to exchange names is a quiet thing, and a product that celebrates it like a
 * jackpot has misunderstood what it is for.
 */
export default function Reveal() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const person = useSpark((s) => s.revealed);
  const setClientState = useSpark((s) => s.setClientState);

  useEffect(() => {
    if (person) setClientState("REVEALED");
  }, [person, setClientState]);

  // The guard. Nothing to reveal means there was no mutual yes in this session,
  // and the honest response is to go back to a screen that is true.
  if (!person) return <Navigate to="/home" replace />;

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="flex h-full flex-col justify-between px-9 pt-20 pb-12"
    >
      <div className="flex flex-col items-center gap-6 text-center">
        <p className="text-xs tracking-[0.2em] text-muted uppercase">
          You both said yes
        </p>

        <motion.div
          initial={reduced ? false : { opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        >
          <Avatar seed={person.avatarSeed} size={112} />
        </motion.div>

        <div className="flex flex-col gap-2">
          <h1 className="text-[2rem] leading-tight font-medium tracking-tight text-text">
            {person.displayName}
          </h1>
          {/* Duration-neutral. The call can end early — by the end-call
              control or through Guardian — so a screen that says "three
              minutes" is wrong for anyone who left at forty seconds, and
              wrong in a way that reads as the product not having noticed. */}
          <p className="text-sm text-muted">
            You spoke without knowing that.
          </p>
        </div>

        {person.sharedInterests.length > 0 ? (
          <div className="flex flex-wrap justify-center gap-2 pt-1">
            {person.sharedInterests.map((interest) => (
              <span
                key={interest}
                className="rounded-pill bg-white/[0.06] px-3 py-1.5 text-[13px] text-text/90 ring-1 ring-white/10 ring-inset"
              >
                {interest}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {/* One action. §5.6: "Then a single action: Add to lock-ins." There is no
          message box, no profile to browse, and nothing to scroll to. */}
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => navigate("/lockins", { replace: true })}
          className="w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-cream transition-opacity hover:opacity-90"
        >
          Add to lock-ins
        </button>
        <p className="text-center text-xs leading-relaxed text-muted">
          Five at a time. That is deliberate.
        </p>
      </div>
    </motion.div>
  );
}
