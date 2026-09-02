import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, Check, ShieldCheck } from "lucide-react";

/**
 * A deliberately simulated Singpass verification hand-off.
 *
 * This is a product mockup, not an identity-provider integration. It never
 * leaves the browser, renders no credential field, and stores no government
 * identifier. The disclosure is repeated on every step so a screenshot cannot
 * accidentally be presented as evidence that Spark is connected to Singpass.
 */
type Step = "intro" | "consent" | "verified";

export function SingpassVerification({
  onComplete,
}: {
  onComplete: () => void;
}) {
  const reduced = useReducedMotion();
  const [step, setStep] = useState<Step>("intro");

  return (
    <div className="flex h-full flex-col overflow-y-auto px-7 pt-14 pb-8">
      <div className="mb-8 flex items-center justify-between">
        <p className="text-sm font-medium tracking-tight text-text">Spark</p>
        <DemoBadge />
      </div>

      <div className="contents">
        {step === "intro" ? (
          <motion.section
            key="intro"
            {...transitionFor(!!reduced)}
            className="flex flex-1 flex-col"
          >
            <div className="mb-7 grid size-14 place-items-center rounded-2xl bg-accent/15 text-accent-soft ring-1 ring-accent/25 ring-inset">
              <ShieldCheck size={28} strokeWidth={1.7} />
            </div>
            <p className="mb-3 text-[10px] tracking-[0.2em] text-muted uppercase">
              Account verification
            </p>
            <h1 className="max-w-[18rem] text-[2rem] leading-[1.08] font-medium tracking-tight text-text">
              Start as a verified person.
            </h1>
            <p className="mt-4 max-w-[19rem] text-sm leading-relaxed text-muted">
              Before profile intake, Spark uses a simulated Singpass check to
              confirm age eligibility and one person per account.
            </p>

            <div className="mt-7 rounded-card bg-surface p-4 ring-1 ring-white/[0.06] ring-inset">
              <div className="flex items-center gap-3">
                <SingpassMark />
                <div>
                  <p className="text-sm font-medium text-text">Singpass verification</p>
                  <p className="mt-0.5 text-xs text-muted">Prototype hand-off</p>
                </div>
              </div>
              <p className="mt-4 border-t border-white/[0.06] pt-4 text-xs leading-relaxed text-muted">
                No real Singpass login occurs, and this demo accepts no
                credentials or identity numbers.
              </p>
            </div>

            <div className="mt-auto pt-8">
              <button
                type="button"
                onClick={() => setStep("consent")}
                className="w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-cream transition-opacity hover:opacity-90"
              >
                Verify with Singpass demo
              </button>
              <p className="mt-3 text-center text-[11px] leading-relaxed text-muted/70">
                Simulation only · no external service is contacted
              </p>
            </div>
          </motion.section>
        ) : null}

        {step === "consent" ? (
          <motion.section
            key="consent"
            {...transitionFor(!!reduced)}
            className="flex flex-1 flex-col"
          >
            <button
              type="button"
              onClick={() => setStep("intro")}
              aria-label="Back to verification introduction"
              className="mb-7 grid size-10 place-items-center rounded-full text-muted transition-colors hover:bg-white/[0.05] hover:text-text"
            >
              <ArrowLeft size={20} />
            </button>

            <div className="mb-6 flex items-center gap-3">
              <SingpassMark />
              <div>
                <p className="text-base font-medium text-text">Singpass verification</p>
                <p className="text-xs text-red-300">Interactive prototype</p>
              </div>
            </div>

            <h1 className="text-[1.65rem] leading-tight font-medium tracking-tight text-text">
              Share two confirmations with Spark?
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              In a real integration, Spark would request the minimum needed to
              establish a verified account.
            </p>

            <div className="mt-6 space-y-3">
              <ConfirmationRow
                title="Age eligibility"
                detail="Confirms only that you are 18 or older"
              />
              <ConfirmationRow
                title="Unique account token"
                detail="Confirms one person can create one Spark account"
              />
            </div>

            <div className="mt-5 rounded-card bg-white/[0.035] p-4 ring-1 ring-white/[0.06] ring-inset">
              <p className="text-[10px] tracking-[0.18em] text-muted uppercase">
                Not shared with Spark
              </p>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                NRIC, full date of birth, address, photo, and Singpass login
                details.
              </p>
            </div>

            <div className="mt-auto pt-8">
              <button
                type="button"
                onClick={() => setStep("verified")}
                className="w-full rounded-pill bg-[#c7353d] px-6 py-4 text-base font-medium text-white transition-opacity hover:opacity-90"
              >
                Approve demo verification
              </button>
              <p className="mt-3 text-center text-[11px] leading-relaxed text-muted/70">
                No data is sent. This button only advances the prototype.
              </p>
            </div>
          </motion.section>
        ) : null}

        {step === "verified" ? (
          <motion.section
            key="verified"
            {...transitionFor(!!reduced)}
            className="flex flex-1 flex-col items-center justify-center text-center"
          >
            <motion.div
              initial={reduced ? false : { scale: 0.72, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
              className="grid size-20 place-items-center rounded-full bg-emerald-400/12 text-emerald-300 ring-1 ring-emerald-400/25 ring-inset"
            >
              <Check size={36} strokeWidth={1.8} />
            </motion.div>
            <p className="mt-7 text-[10px] tracking-[0.2em] text-emerald-300 uppercase">
              Demo verification complete
            </p>
            <h1 className="mt-3 text-[2rem] leading-tight font-medium tracking-tight text-text">
              Verified, without building a profile from your identity.
            </h1>
            <p className="mt-4 max-w-[19rem] text-sm leading-relaxed text-muted">
              Spark received only an 18+ confirmation and a one-way account
              token in this simulation. Your profile starts with what you
              choose to say next.
            </p>

            <button
              type="button"
              onClick={onComplete}
              className="mt-10 w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-cream transition-opacity hover:opacity-90"
            >
              Continue to profile
            </button>
          </motion.section>
        ) : null}
      </div>
    </div>
  );
}

function DemoBadge() {
  return (
    <span className="rounded-pill bg-amber-300/10 px-3 py-1.5 text-[10px] font-medium tracking-[0.14em] text-amber-200 uppercase ring-1 ring-amber-300/20 ring-inset">
      Simulated
    </span>
  );
}

function SingpassMark() {
  return (
    <div
      aria-hidden="true"
      className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#c7353d] text-lg font-semibold text-white shadow-[0_8px_24px_-12px_rgba(199,53,61,0.9)]"
    >
      S
    </div>
  );
}

function ConfirmationRow({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex gap-3 rounded-card bg-surface p-4 ring-1 ring-white/[0.06] ring-inset">
      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-emerald-400/12 text-emerald-300">
        <Check size={12} strokeWidth={2.2} />
      </span>
      <div>
        <p className="text-sm font-medium text-text">{title}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">{detail}</p>
      </div>
    </div>
  );
}

function transitionFor(reduced: boolean) {
  return {
    initial: false as const,
    animate: { opacity: 1, y: 0 },
    transition: {
      duration: reduced ? 0 : 0.24,
      ease: [0.22, 1, 0.36, 1] as const,
    },
  };
}
