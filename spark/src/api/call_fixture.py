"""What the two people in the scripted call actually said.

THE RULE THIS FILE EXISTS TO MAKE UNBREAKABLE

CLAUDE.md: *"Do not let the Communication Agent invent a shared interest.
Prompts must be grounded in something both people actually said. A hallucinated
commonality is a graded fidelity failure and a real user harm."*

The previous fixture broke it. A prompt read "You both mentioned early
mornings", and the two quotes filed as its evidence were "a certification exam
on Thursday" and "birdwatching at the reservoir" — neither of which is about
mornings, and which have nothing in common with each other. The test in place at
the time only checked that ``grounded_in`` held two non-empty strings, so it
passed.

So the grounding is no longer *asserted alongside* a prompt; it is *looked up
from* the transcript. ``shared_grounding()`` searches for the topic in what each
speaker said and raises if either side is missing. A prompt claiming a
commonality that is not in the fixture cannot be constructed at all — the module
fails to import.

Everything here is synthetic. `web/src/api/callFixture.ts` mirrors it, and
`tests/test_wire_contract.py` fails if the two drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Speaker = Literal["local", "remote"]


@dataclass(frozen=True)
class SpokenFact:
    """One thing one person said, filed under a stable topic id.

    The topic is what makes the rule checkable. Deciding whether two English
    sentences are "about the same thing" is not something a unit test can do,
    and a test that tries is a test that quietly stops working. An identifier
    can be compared exactly.
    """

    speaker: Speaker
    topic: str
    quote: str


#: The transcript, such as it is. The only source of evidence in the demo.
SPOKEN_FACTS: tuple[SpokenFact, ...] = (
    SpokenFact("local", "early-mornings", "I am usually up before six"),
    SpokenFact("remote", "early-mornings", "mornings are the only quiet part of my day"),
    SpokenFact("local", "birdwatching", "I have been trying to photograph kingfishers"),
    SpokenFact("remote", "birdwatching", "birdwatching, mostly at the weekend"),
    # Single-sided, and deliberately so. The Continuity Agent cites it in a
    # brief — "she mentioned a certification exam" — which is a fact about the
    # other person, not a claim that the two of them have something in common.
    # It is therefore NOT available to a prompt, and shared_grounding() will
    # refuse to build one from it.
    SpokenFact("remote", "certification-exam", "a certification exam on Thursday"),
)


def said_by(speaker: Speaker, topic: str) -> str | None:
    for fact in SPOKEN_FACTS:
        if fact.speaker == speaker and fact.topic == topic:
            return fact.quote
    return None


def shared_grounding(topic: str) -> tuple[str, str]:
    """The two quotes that let a prompt claim this topic is shared.

    Raises if either person never raised it. That refusal is the feature: it is
    the difference between the agent noticing a commonality and inventing one.
    """
    local = said_by("local", topic)
    remote = said_by("remote", topic)
    if local is None or remote is None:
        missing = "local" if local is None else "remote"
        raise ValueError(
            f"cannot ground a shared prompt in {topic!r}: the {missing} speaker "
            "never raised it. A prompt may only claim a commonality both people "
            "actually stated — see CLAUDE.md, 'do not let the Communication "
            "Agent invent a shared interest'. Either cite a topic both raised, "
            "or word the prompt as a follow-up about one person."
        )
    return local, remote


@dataclass(frozen=True)
class ScriptedPrompt:
    at_second: int
    topic: str
    text: str

    @property
    def grounded_in(self) -> tuple[str, str]:
        """Derived, never hand-written. This is why the wording and the evidence
        cannot drift apart again."""
        return shared_grounding(self.topic)


#: The two moments the mock conversation stalls and the agent has something to
#: offer. Both are worded as the commonality their topic actually supports.
SCRIPTED_PROMPTS: tuple[ScriptedPrompt, ...] = (
    ScriptedPrompt(
        at_second=50,
        topic="early-mornings",
        text="You both mentioned early mornings — ask what gets them up.",
    ),
    ScriptedPrompt(
        at_second=122,
        topic="birdwatching",
        text="You have both brought up birdwatching — ask what they have spotted.",
    ),
)

# Import-time proof. If someone adds a prompt whose topic only one person
# raised, this module stops importing and every test that touches the API
# fails — rather than the demo shipping a fabricated commonality.
for _prompt in SCRIPTED_PROMPTS:
    _prompt.grounded_in


def prompts_as_dicts() -> list[dict]:
    """The wire shape, for `GET /call-script`."""
    return [
        {
            "at_second": prompt.at_second,
            "topic": prompt.topic,
            "text": prompt.text,
            "grounded_in": list(prompt.grounded_in),
        }
        for prompt in SCRIPTED_PROMPTS
    ]


#: What the Continuity Agent cites in a week-one brief. Single-sided on purpose:
#: a brief recalls what the OTHER person said, and attributing it to the wrong
#: speaker is the same class of fidelity error as an invented commonality.
CONTINUITY_CITATION = said_by("remote", "certification-exam")
