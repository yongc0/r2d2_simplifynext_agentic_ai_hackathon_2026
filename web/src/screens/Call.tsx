import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Mic, MicOff, Volume2, VolumeX } from "lucide-react";

import { getAdapter } from "../api/adapter";
import type { CallTick, ConversationPrompt } from "../api/adapter";
import { CountdownRing } from "../components/CountdownRing";
import {
  GuardianOverlay,
  GuardianTrigger,
  useGuardian,
} from "../components/Guardian";
import { Waveform } from "../components/Waveform";
import { SHOW_HANDLE_PRE_REVEAL } from "../api/wire";
import { ENTRY_STATES, fallbackFor, useEntryState } from "../routes/guard";
import { useSpark } from "../store/useSpark";

/**
 * /call — the hero screen (FRONTEND.md §5.4).
 *
 * INVARIANT 4: there is no extend control anywhere in this tree, and there must
 * never be one. 180 seconds is a MAXIMUM. A test sweeps every control on the
 * screen for one rather than trusting that nobody adds one.
 *
 * There IS an end-call control, and it is a safety feature rather than a
 * convenience. ARCHITECTURE §13.8 and docs/PILOT.md both argue that the call is
 * safe without audio screening because its mitigations are structural — three
 * minutes, anonymous on both sides, no identity without a mutual yes, and
 * "either party can end it". That last one was documented and not built, which
 * made the safety argument false. A three-minute maximum must never become a
 * three-minute minimum: the person who wants out at 0:20 is exactly the person
 * the mitigation is for.
 *
 * Ending early routes to the SAME place the timer does, so nothing downstream
 * can tell the two apart — see `endCall`.
 *
 * INVARIANT 2: the only thing shown about the other person is a pseudonymous
 * handle. No name, no photo, no age, no silhouette — and `EncounterCard`, which
 * is all this screen has access to, has no field for any of them.
 *
 * On the clock. Elapsed time is `performance.now()` minus a start stamp, read
 * fresh every animation frame. It is deliberately NOT an interval that adds
 * 1000ms to a counter: that drifts by seconds across three minutes, and a
 * screen recorder competing for the main thread makes it worse. The ring, the
 * digits and the auto-advance all read the same monotonic source, so they
 * cannot disagree on camera.
 */
export default function Call() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const setClientState = useSpark((s) => s.setClientState);
  const flagConcern = useSpark((s) => s.flagGuardianConcern);

  /**
   * Tell the server how the check-in was answered.
   *
   * Deliberately not awaited, and its failure is deliberately swallowed. A
   * person using a safety exit must never be held up by a request, and an error
   * about logging is the last thing they need to read at that moment. The
   * consequence they can SEE — the encounter closing without the reveal gate
   * opening — happens locally and does not depend on this.
   */
  const reportCheckIn = (allRight: boolean) => {
    void getAdapter()
      .recordGuardianCheckIn(encounterId ?? "", allRight)
      .catch(() => {});
  };
  // GUARD. You cannot be in a call you never accepted — see routes/guard.ts.
  const entry = useEntryState();
  const allowed = ENTRY_STATES.call.has(entry);
  // `HttpAdapter` needs the id to fetch a script; `MockAdapter` ignores it.
  const encounterId = useSpark((s) => s.card?.encounterId);

  const [total, setTotal] = useState(180);
  const [remaining, setRemaining] = useState(180);
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [prompt, setPrompt] = useState<ConversationPrompt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const guardian = useGuardian();

  // Written every frame, read by the canvas. Never state: sixty rerenders a
  // second would take the ring and the digits with it.
  const amplitudeRef = useRef(0.05);
  const speakerRef = useRef<CallTick["speaker"]>("silence");

  // Hoisted out of the effect so the end-call button can stop the same loop the
  // timer does. One frame handle, one guard, one exit.
  const rafRef = useRef(0);
  const endedRef = useRef(false);

  /**
   * The one way out of this screen, used by BOTH the timer and the button.
   *
   * Sharing the exit is what keeps the two indistinguishable. If ending early
   * had its own route, its own delay, or its own state, then how a call ended
   * would be legible downstream — and eventually to the other person. It does
   * not, so it is not.
   *
   * Guarded, because the last animation frame can land in the same tick as a
   * click, and navigating twice would put a stray entry in the history.
   */
  const endCall = () => {
    if (endedRef.current) return;
    stopClock();
    leave();
  };

  /**
   * Stop the call without leaving the screen.
   *
   * Guardian needs this: the check-in belongs to the moment after stepping
   * away, and navigating first would unmount the overlay before the person
   * could answer it. Marking the call ended here also stops the timer firing
   * mid-check-in and yanking them to the next screen.
   */
  const stopClock = () => {
    endedRef.current = true;
    cancelAnimationFrame(rafRef.current);
  };

  /** Go to the gate. Every exit from this screen ends up here. */
  const leave = () => {
    setClientState("CALL_ENDED");
    navigate("/call/consent", { replace: true });
  };

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    const adapter = getAdapter();

    (async () => {
      let ticks: CallTick[];
      let prompts: ConversationPrompt[];
      try {
        ({ ticks, prompts } = await adapter.getCallScript(encounterId ?? ""));
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
        return;
      }
      if (cancelled) return;

      // An empty script is not something to limp along with: every frame below
      // indexes `ticks`, and `ticks[0]` on an empty array is how a blank screen
      // becomes a crash mid-recording. Say so instead.
      if (ticks.length === 0) {
        setError(
          "The call script came back empty, so there is nothing to play. " +
            "Check the backend is running, or unset VITE_API to use MockAdapter.",
        );
        return;
      }

      const duration = ticks.at(-1)?.elapsed ?? 180;
      setTotal(duration);
      setRemaining(duration);
      setClientState("CONNECTED");

      const startedAt = performance.now();
      let shownPromptAt = -1;

      const frame = () => {
        const elapsed = (performance.now() - startedAt) / 1000;
        const left = Math.max(0, duration - elapsed);
        setRemaining(left);

        // Interpolate between whole-second ticks so the waveform moves at frame
        // rate rather than stepping once a second.
        const i = Math.min(ticks.length - 1, Math.floor(elapsed));
        const next = ticks[Math.min(ticks.length - 1, i + 1)];
        const t = elapsed - Math.floor(elapsed);
        amplitudeRef.current =
          ticks[i].amplitude * (1 - t) + next.amplitude * t;
        speakerRef.current = ticks[i].speaker;

        // A grounded suggestion, when the conversation has stalled.
        //
        // Tracked in `shownPromptAt` rather than by reading the `prompt` state:
        // this loop is created once, so any state it closed over would be the
        // mount-time value forever, and the withdraw branch would never fire.
        const due = prompts.find(
          (p) => elapsed >= p.atSecond && elapsed < p.atSecond + 12,
        );
        if (due) {
          if (due.atSecond !== shownPromptAt) {
            shownPromptAt = due.atSecond;
            setPrompt(due);
          }
        } else if (shownPromptAt !== -1) {
          shownPromptAt = -1;
          setPrompt(null);
        }

        if (left <= 0) {
          // INVARIANT 4. The hard stop. Nothing on this screen can push it
          // later; the end-call button can only bring it forward.
          endCall();
          return;
        }
        rafRef.current = requestAnimationFrame(frame);
      };

      rafRef.current = requestAnimationFrame(frame);
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
    // Mount-only: the clock must not restart when a control is toggled.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!allowed) return <Navigate to={fallbackFor(entry)} replace />;

  if (error) {
    // Visible and actionable, rather than a screen that sits at 3:00 forever.
    // The call cannot be recovered by retrying a script that is not there, so
    // the only honest action is to leave.
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-9 text-center">
        <h1 className="text-xl font-medium text-text">
          The call could not be started.
        </h1>
        <p className="text-sm leading-relaxed text-muted">{error}</p>
        <button
          type="button"
          onClick={() => navigate("/home", { replace: true })}
          className="mt-2 rounded-pill bg-white/[0.06] px-6 py-3 text-sm text-text transition-colors hover:bg-white/[0.1]"
        >
          Back
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col justify-between px-7 pb-10 pt-14">
      {/* --- who, as far as anyone is allowed to know ------------------ */}
      <header className="flex flex-col items-center gap-1.5">
        <p className="text-xs tracking-[0.2em] text-muted uppercase">
          Anonymous call
        </p>
        {SHOW_HANDLE_PRE_REVEAL ? (
          <p className="font-mono text-sm text-accent-soft">azure-heron</p>
        ) : null}
      </header>

      {/* --- the three minutes ----------------------------------------- */}
      <div className="flex flex-col items-center gap-9">
        <CountdownRing remaining={remaining} total={total} />
        <Waveform amplitudeRef={amplitudeRef} speakerRef={speakerRef} />
      </div>

      {/* --- controls --------------------------------------------------
          Mute, speaker, Guardian, and End call. Note what is NOT here and
          never will be: an extend, an "add time", a "just five more minutes".
          INVARIANT 4 is about lengthening the call, not about being trapped in
          one. */}
      <div className="flex flex-col items-center gap-7">
        <div className="flex items-center gap-5">
          <ControlButton
            label={muted ? "Unmute" : "Mute"}
            active={muted}
            onClick={() => setMuted((m) => !m)}
          >
            {muted ? <MicOff size={20} /> : <Mic size={20} />}
          </ControlButton>

          <ControlButton
            label={speakerOn ? "Speaker off" : "Speaker on"}
            active={!speakerOn}
            onClick={() => setSpeakerOn((s) => !s)}
          >
            {speakerOn ? <Volume2 size={20} /> : <VolumeX size={20} />}
          </ControlButton>

          {/* Guardian — §5.8. Discreet and unlabelled: recognisable to the
              person who set it up, unremarkable to anyone watching over their
              shoulder. Styled unmistakably in-app, never as system chrome
              (INVARIANT 6) — see `Guardian.tsx`. */}
          <GuardianTrigger onTrigger={guardian.trigger} />
        </div>

        <button
          type="button"
          onClick={endCall}
          className="rounded-pill bg-red-600 px-7 py-3 text-sm font-semibold text-white ring-1 ring-red-700 ring-inset transition-colors hover:bg-red-700"
        >
          End call
        </button>

        <p className="text-center text-xs leading-relaxed text-muted">
          Ends automatically at three minutes. You can leave sooner.
        </p>
      </div>

      {/* --- the Communication Agent's suggestion -----------------------
          Slides up from the bottom, clearly a suggestion, never a takeover.
          Grounded in what BOTH people said — the agent may not invent a
          shared interest, so a prompt it cannot ground is simply not shown. */}
      <AnimatePresence>
        {prompt ? (
          <motion.div
            initial={reduced ? false : { y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { y: 80, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-x-5 bottom-5 rounded-card bg-surface/95 p-4 shadow-[0_20px_40px_-12px_rgba(0,0,0,0.6)] ring-1 ring-white/[0.06] backdrop-blur"
            role="status"
          >
            <p className="mb-1 text-[10px] tracking-[0.18em] text-accent-soft uppercase">
              Suggested
            </p>
            <p className="text-sm leading-relaxed text-text">{prompt.text}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Guardian's interruption and the private check-in that follows it.
          "Step away now" ends the call through `endCall`, the same exit the
          timer uses — so leaving via Guardian is indistinguishable downstream
          from leaving any other way, which is the entire point of it. */}
      <GuardianOverlay
        stage={guardian.stage}
        onDismiss={guardian.dismiss}
        onStepAway={() => {
          // The call stops immediately; the screen stays up for the check-in.
          stopClock();
          guardian.stepAway();
        }}
        onFine={() => {
          reportCheckIn(true);
          guardian.finish();
          leave();
        }}
        onConcern={() => {
          // A CONSEQUENCE, not an acknowledgement. The encounter closes without
          // the reveal gate ever opening, so there is no path from here to
          // exchanging names with someone who has just been flagged. The
          // close-out is the same one every other non-connection reaches, so
          // the other party learns nothing about why.
          reportCheckIn(false);
          guardian.finish();
          flagConcern();
          setClientState("CLOSED");
          navigate("/encounter/closed", { replace: true });
        }}
      />
    </div>
  );
}

function ControlButton({
  children,
  label,
  active,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={`grid size-14 place-items-center rounded-full transition-colors ${
        active
          ? "bg-text text-bg"
          : "bg-white/[0.06] text-text hover:bg-white/[0.1]"
      }`}
    >
      {children}
    </button>
  );
}
