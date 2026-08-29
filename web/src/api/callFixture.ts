/**
 * What the two people in the scripted call actually said.
 *
 * The mirror of `spark/src/api/call_fixture.py`, and kept in step by
 * `spark/tests/test_wire_contract.py`.
 *
 * THE RULE THIS FILE EXISTS TO MAKE UNBREAKABLE
 *
 * CLAUDE.md: "Do not let the Communication Agent invent a shared interest.
 * Prompts must be grounded in something both people actually said. A
 * hallucinated commonality is a graded fidelity failure and a real user harm."
 *
 * The previous fixture broke it. A prompt read "You both mentioned early
 * mornings", and the two quotes filed as its evidence were "a certification
 * exam on Thursday" and "birdwatching at the reservoir" — neither about
 * mornings, and with nothing in common with each other. The test only checked
 * that `groundedIn` held two non-empty strings, so it passed.
 *
 * So grounding is no longer written NEXT TO a prompt; it is LOOKED UP from the
 * transcript. `sharedGrounding()` throws when a topic is not something both
 * people raised, so a prompt claiming a commonality that is not there cannot be
 * built — the module fails to load.
 */

export type Speaker = "local" | "remote";

/**
 * One thing one person said, filed under a stable topic id.
 *
 * The topic is what makes the rule checkable. Whether two English sentences are
 * "about the same thing" is not something a unit test can decide, and a test
 * that tries is one that quietly stops working. An identifier compares exactly.
 */
export interface SpokenFact {
  speaker: Speaker;
  topic: string;
  quote: string;
}

/** The transcript, such as it is. The only source of evidence in the demo. */
export const SPOKEN_FACTS: SpokenFact[] = [
  { speaker: "local", topic: "early-mornings", quote: "I am usually up before six" },
  { speaker: "remote", topic: "early-mornings", quote: "mornings are the only quiet part of my day" },
  { speaker: "local", topic: "birdwatching", quote: "I have been trying to photograph kingfishers" },
  { speaker: "remote", topic: "birdwatching", quote: "birdwatching, mostly at the weekend" },
  // Single-sided, deliberately. The Continuity Agent cites this in a brief —
  // "she mentioned a certification exam" — which is a fact about the OTHER
  // person, not a claim that the two of them share something. It is therefore
  // not available to a prompt, and `sharedGrounding` refuses to build one.
  { speaker: "remote", topic: "certification-exam", quote: "a certification exam on Thursday" },
];

export function saidBy(speaker: Speaker, topic: string): string | null {
  const fact = SPOKEN_FACTS.find((f) => f.speaker === speaker && f.topic === topic);
  return fact ? fact.quote : null;
}

/**
 * The two quotes that let a prompt claim this topic is shared.
 *
 * Throws if either person never raised it. That refusal is the feature — it is
 * the difference between the agent noticing a commonality and inventing one.
 */
export function sharedGrounding(topic: string): [string, string] {
  const local = saidBy("local", topic);
  const remote = saidBy("remote", topic);
  if (local === null || remote === null) {
    const missing = local === null ? "local" : "remote";
    throw new Error(
      `cannot ground a shared prompt in "${topic}": the ${missing} speaker ` +
        "never raised it. A prompt may only claim a commonality both people " +
        "actually stated — see CLAUDE.md, 'do not let the Communication Agent " +
        "invent a shared interest'. Cite a topic both raised, or word the " +
        "prompt as a follow-up about one person.",
    );
  }
  return [local, remote];
}

/** A prompt before its evidence is attached. */
interface PromptSeed {
  atSecond: number;
  topic: string;
  text: string;
}

/**
 * The two moments the mock conversation stalls and the agent has something to
 * offer. Both are worded as the commonality their topic actually supports.
 */
const PROMPT_SEEDS: PromptSeed[] = [
  {
    atSecond: 50,
    topic: "early-mornings",
    text: "You both mentioned early mornings — ask what gets them up.",
  },
  {
    atSecond: 122,
    topic: "birdwatching",
    text: "You have both brought up birdwatching — ask what they have spotted.",
  },
];

export interface GroundedPrompt extends PromptSeed {
  groundedIn: [string, string];
}

/**
 * Built at module load, so an ungroundable prompt is a load-time failure rather
 * than something a viewer discovers on camera.
 */
export const SCRIPTED_PROMPTS: GroundedPrompt[] = PROMPT_SEEDS.map((seed) => ({
  ...seed,
  groundedIn: sharedGrounding(seed.topic),
}));

/**
 * What the Continuity Agent cites in a week-one brief.
 *
 * Single-sided on purpose, and read from the REMOTE speaker: a brief recalls
 * what the other person said. The previous fixture stored this under a constant
 * named `SAID_BY_LOCAL` and then rendered it as "She mentioned …", attributing
 * the user's own words to the person they had just met — the same class of
 * fidelity error as an invented commonality, and just as invisible.
 */
export const CONTINUITY_CITATION = saidBy("remote", "certification-exam")!;
