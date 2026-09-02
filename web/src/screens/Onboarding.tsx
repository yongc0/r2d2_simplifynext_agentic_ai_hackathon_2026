import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { getAdapter } from "../api/adapter";
import { KNOWN_TRAITS } from "../api/extract";
import type { ChipKind, Intent, ProfileChip } from "../api/types";
import { SingpassVerification } from "../components/SingpassVerification";
import { ForeignerSignup } from "../components/ForeignerSignup";
import { intentLabel } from "../api/wire";
import { useSpark } from "../store/useSpark";

/**
 * /onboarding — simulated verification, then conversational intake (§5.1).
 *
 * Chat, not a form. The agent asks one thing at a time, the person answers in
 * their own words, and what was understood appears as chips in the panel above
 * — animated in as they are captured. FRONTEND.md calls that "the shot that
 * sells the Onboarding Agent in three seconds", and it is the reason this
 * screen is a conversation rather than four dropdowns.
 *
 * TWO THINGS HERE ARE SAFETY, NOT DESIGN
 *
 * 1. INTENT IS NEVER INFERRED. The final step offers the three options as
 *    buttons, and pressing one appends a sentence that NAMES the intent to the
 *    transcript. The extraction then finds it the ordinary way. There is no
 *    path in this file that sets an intent directly — the button is the person
 *    saying it, not the screen deciding for them. (ARCHITECTURE §13.1, and
 *    `spark/tests/test_intent.py` holds the same line on the Python side.)
 *
 * 2. NO HEIGHT, APPEARANCE OR PHOTO FIELD — invariant 9.5. There is no such
 *    input, and `ChipKind` has no member one could be rendered as, so this is
 *    structural rather than a matter of remembering. `extract.ts` additionally
 *    strips those words before matching, so volunteering one captures nothing.
 */

/**
 * How long the agent "thinks" before replying.
 *
 * Long enough to read as a conversation rather than a form submit, short enough
 * that a five-minute recording is not mostly waiting. One constant so every
 * turn is paced identically — a variable delay would read as the agent finding
 * some answers harder than others.
 */
const AGENT_DELAY_MS = 600;

/** The opening question. Deliberately open — it is not asking for a checklist. */
const OPENING =
  "Hello. Tell me a little about how you spend your time, and what matters to you.";

const COMPLETE =
  "That is everything I need. I will update your You profile with what you shared.";

interface Message {
  from: "agent" | "user";
  text: string;
}

const REQUIRED_TOPICS: Array<{ topic: string; kind: ChipKind; question: string }> = [
  { topic: "intent", kind: "intent", question: "What are you hoping to find here?" },
  { topic: "interests", kind: "interest", question: "What interests or hobbies do you enjoy?" },
  { topic: "characteristics", kind: "trait", question: "Which characteristics best describe you?" },
  { topic: "values", kind: "value", question: "What matters most to you in a relationship or friendship?" },
  { topic: "languages", kind: "language", question: "Which languages are you comfortable speaking?" },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const setChips = useSpark((s) => s.setChips);
  const setProfilePhoto = useSpark((s) => s.setProfilePhoto);
  const chips = useSpark((s) => s.chips);

  /**
   * The verification mockup comes first, but it is deliberately not sent to
   * the adapter: there is no Singpass integration and no real identity data.
   * It is a filmable product concept whose disclosure says exactly that.
   */
  const [verificationComplete, setVerificationComplete] = useState(false);
  const [foreignerSignup, setForeignerSignup] = useState(false);

  const [messages, setMessages] = useState<Message[]>([
    { from: "agent", text: OPENING },
  ]);
  const [draft, setDraft] = useState("");
  const [selectedTraits, setSelectedTraits] = useState<string[]>([]);
  const [openingAnswered, setOpeningAnswered] = useState(false);
  const [thinking, setThinking] = useState(false);
  /** True once the agent has nothing left to ask. */
  const [complete, setComplete] = useState(false);
  /** True when the agent is waiting on an intent it may not infer. */
  const [askingIntent, setAskingIntent] = useState(false);
  const [askingTopic, setAskingTopic] = useState<string | null>(null);

  /** Everything the person has actually said, in order. The extraction runs
   *  over the whole of it, never over the latest message alone. */
  const transcript = useRef<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);

  // Keep the newest message in view. Assigned rather than animated: a scroll
  // animation racing a chip animation is the kind of jitter that shows up on
  // film and nowhere else.
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const send = async (text: string) => {
    const said = text.trim();
    if (!said || thinking || complete) return;

    setDraft("");
    if (transcript.current.length === 0) setOpeningAnswered(true);
    setSelectedTraits([]);
    setAskingIntent(false);
    setAskingTopic(null);
    setMessages((m) => [...m, { from: "user", text: said }]);
    transcript.current.push(said);
    setThinking(true);

    const turn = await getAdapter().extractProfile(transcript.current.join(" "));

    // The pause is after the work, not instead of it: the agent has genuinely
    // finished before the reply appears.
    await new Promise((resolve) => setTimeout(resolve, AGENT_DELAY_MS));

    const merged = [...chips, ...turn.chips].filter(
        (chip, index, all) =>
          all.findIndex(
            (candidate) => candidate.kind === chip.kind && candidate.label === chip.label,
          ) === index,
      );
    setChips(merged);
    setThinking(false);

    const next = REQUIRED_TOPICS.find(
      ({ kind }) => !merged.some((chip) => chip.kind === kind),
    );
    if (next) {
      setMessages((m) => [...m, { from: "agent", text: next.question }]);
      const needsIntent = next.topic === "intent";
      setAskingIntent(needsIntent);
      setAskingTopic(next.topic);
    } else {
      setMessages((m) => [...m, { from: "agent", text: COMPLETE }]);
      setComplete(true);
    }
  };

  const sendDraft = () => {
    const traitSentence = selectedTraits.length
      ? `I would describe myself as ${selectedTraits.join(", ")}.`
      : "";
    send(
      !openingAnswered
        ? [draft.trim(), traitSentence].filter(Boolean).join(" ")
        : draft,
    );
  };

  const stage = complete
    ? 5
    : Math.max(1, REQUIRED_TOPICS.findIndex(({ topic }) => topic === askingTopic) + 1);
  const composerPlaceholder = !openingAnswered
    ? "Or describe yourself in your own words"
    : askingIntent
      ? "Or type what you are looking for"
      : askingTopic === "interests"
        ? "Tell us about your interests"
        : askingTopic === "characteristics"
          ? "Describe your characteristics"
          : askingTopic === "values"
            ? "Share what matters to you"
            : askingTopic === "languages"
              ? "List the languages you speak"
              : "Add anything else you want Spark to know";

  if (!verificationComplete) {
    if (foreignerSignup) {
      return (
        <ForeignerSignup
          onBack={() => setForeignerSignup(false)}
          onComplete={(result) => {
            setChips(result.chips);
            setProfilePhoto(result.profilePhoto);
            setVerificationComplete(true);
          }}
        />
      );
    }
    return (
      <SingpassVerification
        onComplete={() => setVerificationComplete(true)}
        onForeigner={() => setForeignerSignup(true)}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <ChipPanel chips={chips} reduced={!!reduced} />

      <div
        ref={scroller}
        className="no-scrollbar flex-1 space-y-3 overflow-y-auto px-6 py-5"
      >
        <OnboardingProgress stage={stage} thinking={thinking} />
        {messages.map((message, i) => (
          <Bubble key={i} message={message} reduced={!!reduced} />
        ))}
        {!openingAnswered && !thinking ? (
          <TraitChoice
            selected={selectedTraits}
            onChange={setSelectedTraits}
            onContinue={sendDraft}
          />
        ) : null}
        {thinking ? <Thinking /> : null}
      </div>

      <div className="border-t border-white/[0.06] px-5 pt-4 pb-8">
        {complete ? (
          <button
            type="button"
            onClick={() => navigate("/home", { replace: true })}
            className="w-full rounded-pill bg-accent px-6 py-4 text-base font-medium text-cream transition-opacity hover:opacity-90"
          >
            Continue
          </button>
        ) : (
          <div className="flex flex-col gap-3">
            {askingIntent ? <IntentChoice onChoose={send} /> : null}
            {askingTopic && askingTopic !== "intent" ? (
              <TopicChoice topic={askingTopic} onChoose={send} />
            ) : null}
            <Composer
              value={draft}
              onChange={setDraft}
              onSend={sendDraft}
              disabled={thinking}
              placeholder={composerPlaceholder}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The chip panel — the live extraction
// ---------------------------------------------------------------------------

/** Colour per kind, so the panel reads as structure rather than a word cloud. */
const CHIP_STYLE: Record<ChipKind, string> = {
  intent: "bg-navy text-cream ring-navy",
  trait: "bg-peach/65 text-ink ring-clay/25",
  interest: "bg-cream text-navy ring-navy/15",
  value: "bg-clay/15 text-clay ring-clay/25",
  availability: "bg-peach text-navy ring-clay/20",
  language: "bg-emerald-100 text-emerald-800 ring-emerald-300",
};

function ChipPanel({
  chips,
  reduced,
}: {
  chips: ProfileChip[];
  reduced: boolean;
}) {
  return (
    // FIXED height, not min-height. The panel fills from empty to full during
    // the take, and a container that grew with it would push the conversation
    // down the screen mid-sentence.
    <div
      className="h-[184px] shrink-0 border-b border-white/[0.06] px-6 pt-14 pb-4"
      aria-live="polite"
      aria-label="What the agent has understood"
    >
      <p className="mb-3 font-mono text-[10px] tracking-[0.2em] text-muted uppercase">
        Understood so far
      </p>

      {chips.length === 0 ? (
        <p className="text-sm leading-relaxed text-muted/60">
          Nothing yet — this fills in as you talk.
        </p>
      ) : (
        <div className="no-scrollbar flex h-[104px] flex-wrap content-start gap-2 overflow-y-auto">
          <AnimatePresence initial={false}>
            {chips.map((chip) => (
              <motion.span
                key={`${chip.kind}:${chip.label}`}
                initial={reduced ? false : { opacity: 0, scale: 0.86, y: 6 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                className={`rounded-pill px-3 py-1.5 text-[13px] ring-1 ring-inset ${CHIP_STYLE[chip.kind]}`}
              >
                {chip.label}
              </motion.span>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The conversation
// ---------------------------------------------------------------------------

function Bubble({
  message,
  reduced,
}: {
  message: Message;
  reduced: boolean;
}) {
  const fromAgent = message.from === "agent";
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={fromAgent ? "flex justify-start" : "flex justify-end"}
    >
      <p
        className={
          fromAgent
            ? "max-w-[80%] rounded-card rounded-bl-md bg-surface px-4 py-3 text-[15px] leading-relaxed text-text ring-1 ring-navy/10 ring-inset"
            : "max-w-[80%] rounded-card rounded-br-md bg-accent/90 px-4 py-3 text-[15px] leading-relaxed text-cream"
        }
      >
        {message.text}
      </p>
    </motion.div>
  );
}

function Thinking() {
  return (
    <div className="flex justify-start" aria-label="The agent is thinking">
      <div className="flex gap-1.5 rounded-card rounded-bl-md bg-surface px-4 py-4">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-muted"
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.16 }}
          />
        ))}
      </div>
    </div>
  );
}

function OnboardingProgress({
  stage,
  thinking,
}: {
  stage: number;
  thinking: boolean;
}) {
  const labels = ["Intent", "Interests", "Characteristics", "Values", "Languages"];
  return (
    <div className="pb-1" aria-label={`Onboarding step ${stage} of 5`}>
      <div className="mb-2 flex gap-1.5" aria-hidden="true">
        {labels.map((label, index) => (
          <span
            key={label}
            className={`h-1 flex-1 rounded-full ${index < stage ? "bg-accent" : "bg-white/[0.08]"}`}
          />
        ))}
      </div>
      <p className="text-[11px] font-semibold tracking-[0.12em] text-navy uppercase">
        {thinking ? "Understanding your reply" : `Step ${stage} of 5 · ${labels[stage - 1]}`}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function Composer({
  value,
  onChange,
  onSend,
  disabled,
  placeholder,
}: {
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  disabled: boolean;
  placeholder: string;
}) {
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label="Your reply"
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-pill bg-surface px-5 py-3.5 text-[15px] text-text placeholder:text-muted/50 focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || value.trim().length === 0}
        className="shrink-0 rounded-pill bg-accent px-5 py-3.5 text-sm font-medium text-cream transition-opacity hover:opacity-90 disabled:opacity-30"
      >
        Send
      </button>
    </form>
  );
}

const MAX_TRAITS = 5;

function TraitChoice({
  selected,
  onChange,
  onContinue,
}: {
  selected: string[];
  onChange: (traits: string[]) => void;
  onContinue: () => void;
}) {
  const toggle = (trait: string) => {
    if (selected.includes(trait)) {
      onChange(selected.filter((item) => item !== trait));
    } else if (selected.length < MAX_TRAITS) {
      onChange([...selected, trait]);
    }
  };

  return (
    <div
      className="rounded-card bg-surface/70 p-4 ring-1 ring-white/[0.06] ring-inset"
      aria-label="Choose traits that sound like you"
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-text">Choose a few traits</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            Optional — select up to five, or write your own reply below.
          </p>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-muted">
          {selected.length}/{MAX_TRAITS}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {KNOWN_TRAITS.map((trait) => {
          const active = selected.includes(trait);
          const unavailable = !active && selected.length >= MAX_TRAITS;
          return (
            <button
              key={trait}
              type="button"
              aria-pressed={active}
              disabled={unavailable}
              onClick={() => toggle(trait)}
              className={`rounded-pill px-3 py-2 text-sm capitalize ring-1 ring-inset transition-colors disabled:opacity-35 ${
                active
                  ? "bg-accent/25 text-accent-soft ring-accent/40"
                  : "bg-white/[0.04] text-text/85 ring-white/10 hover:bg-white/[0.08]"
              }`}
            >
              {trait}
            </button>
          );
        })}
      </div>
      {selected.length > 0 ? (
        <button
          type="button"
          onClick={onContinue}
          className="mt-4 w-full rounded-pill bg-accent px-5 py-3 text-sm font-medium text-cream transition-opacity hover:opacity-90"
        >
          Continue with {selected.length} {selected.length === 1 ? "trait" : "traits"}
        </button>
      ) : null}
    </div>
  );
}

/**
 * The intent question, as three buttons.
 *
 * Each button sends a SENTENCE, not a value. That is the whole point: the
 * extraction still has to find a named intent in the transcript, so this screen
 * has no privileged route to setting one. Delete this component and intake
 * still works — the person can type the same words.
 *
 * The order is fixed and nothing is preselected or emphasised. A default here
 * would be a nudge, and a nudge is inferring intent with extra steps.
 */
const INTENT_SENTENCES: [Intent, string][] = [
  ["partner_long_term", "I am looking for something long term."],
  ["partner_short_term", "I am looking for something short term."],
  ["friends", "I am looking to make friends."],
];

function IntentChoice({ onChoose }: { onChoose: (text: string) => void }) {
  return (
    <div className="flex flex-col gap-2" aria-label="Choose what you are looking for">
      {INTENT_SENTENCES.map(([intent, sentence]) => (
        <button
          key={intent}
          type="button"
          onClick={() => onChoose(sentence)}
          className="w-full rounded-pill bg-surface px-6 py-3.5 text-[15px] text-text ring-1 ring-white/[0.06] ring-inset transition-colors hover:bg-white/[0.07]"
        >
          {intentLabel(intent)}
        </button>
      ))}
    </div>
  );
}

const TOPIC_OPTIONS: Record<string, string[]> = {
  interests: ["Coffee", "Reading", "Cooking", "Running", "Photography", "Live music"],
  characteristics: ["Curious", "Creative", "Outgoing", "Calm", "Playful", "Thoughtful"],
  values: ["Honesty", "Kindness", "Ambition", "Family", "Humour", "Curiosity"],
  languages: ["English", "Mandarin", "Malay", "Tamil", "Cantonese", "Hokkien"],
};

function TopicChoice({ topic, onChoose }: { topic: string; onChoose: (text: string) => void }) {
  const options = TOPIC_OPTIONS[topic] ?? [];
  return (
    <div className="grid grid-cols-2 gap-2" aria-label={`Choose ${topic}`}>
      {options.map((label) => (
        <button
          key={label}
          type="button"
          onClick={() => onChoose(label)}
          className="rounded-card bg-surface px-4 py-3.5 text-sm font-medium text-text ring-1 ring-navy/15 ring-inset transition-colors hover:bg-cream"
        >
          {label}
        </button>
      ))}
    </div>
  );
}
