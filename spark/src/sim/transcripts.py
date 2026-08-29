"""Synthetic intake transcripts — what someone says when they sign up.

Spark's MVP chain starts with onboarding, so the demo has to start there too.
This turns a persona back into the kind of thing a person would actually type,
which the Onboarding Agent then reads forward into a `Profile`.

Deliberately messy. Real intake is hedged, out of order, and full of things the
system must ignore: an aside about being tall, a tone that sounds serious
without naming an intent. A generator that produced tidy sentences would make
the Extraction agent look better than it is, and would never exercise the rule
that matters — that intent is never inferred from tone.

Everything here is fictional, and no transcript contains a real person's words.
"""

from __future__ import annotations

import random

from src.schemas.core import Intent, TimeBucket

_INTENT_PHRASING: dict[Intent, tuple[str, ...]] = {
    Intent.PARTNER_LONG_TERM: (
        "I'm after something long-term, if I'm honest.",
        "I'd like to settle down eventually.",
        "Looking for something serious this time.",
    ),
    Intent.PARTNER_SHORT_TERM: (
        "Something casual for now.",
        "Nothing serious — happy to see where it goes.",
        "Short-term is fine by me.",
    ),
    Intent.FRIENDS: (
        "Mostly I want to make friends here.",
        "Strictly platonic, I've just moved.",
        "Looking for friendship more than anything.",
    ),
}

_BUCKET_PHRASING: dict[TimeBucket, str] = {
    TimeBucket.EARLY_MORNING: "I'm up early, before work usually.",
    TimeBucket.MORNING: "Mornings are when I'm most awake.",
    TimeBucket.MIDDAY: "Lunch is about the only gap I get.",
    TimeBucket.AFTERNOON: "Afternoons, mostly.",
    TimeBucket.EVENING: "Evenings after work are easiest.",
    TimeBucket.NIGHT: "I'm a night person, late is fine.",
}

#: Asides that must be ignored: appearance, and tone that sounds like intent
#: without naming one. Both are here on purpose — a demo where the tricky cases
#: never appear demonstrates nothing.
_NOISE = (
    "I'm quite tall, if that matters.",
    "People say I'm serious but I don't think I am.",
    "I've been on the apps for years and I'm tired of it.",
    "My last relationship ended badly, so I'm taking it slowly.",
    "I don't photograph well, for what it's worth.",
)

_OPENERS = (
    "Hi — not sure how much to write here.",
    "Right, let me try this.",
    "Okay. Where do I start.",
)


def transcript_for(persona, rng: random.Random | None = None) -> str:
    """A plausible intake transcript for one persona.

    Deterministic given a seeded `rng`, so the demo says the same thing twice.
    """
    rng = rng or random.Random(hash(persona.id) & 0xFFFF)
    lines = [rng.choice(_OPENERS)]

    if persona.user.profile.interests:
        shown = persona.user.profile.interests[:3]
        lines.append(
            f"I'm into {', '.join(shown[:-1])} and {shown[-1]}."
            if len(shown) > 1
            else f"I'm into {shown[0]}."
        )
    if persona.user.profile.values:
        lines.append(f"I care a lot about {persona.user.profile.values[0]}.")

    # An aside the extraction must drop, before the intent — so a naive reader
    # has every chance to be led astray by it.
    lines.append(rng.choice(_NOISE))

    for intent in persona.user.profile.intents:
        lines.append(rng.choice(_INTENT_PHRASING[intent]))

    for bucket in persona.user.profile.availability_window[:2]:
        lines.append(_BUCKET_PHRASING[bucket])

    if len(persona.user.profile.languages) > 1:
        others = [lang for lang in persona.user.profile.languages if lang != "english"]
        if others:
            lines.append(f"I speak English and {others[0].title()}.")

    return " ".join(lines)


def silent_on_intent_transcript() -> str:
    """A transcript that says a great deal and never names an intent.

    The case §13.1 is about. A system that reads an intent out of this is
    guessing, and the Onboarding Agent must ask instead.
    """
    return (
        "Right, let me try this. I've been on the apps for years and I'm tired "
        "of it. I like climbing and old films, and I'm around most evenings. "
        "People say I'm serious but I don't think I am. My last relationship "
        "ended badly, so I'm taking it slowly."
    )
