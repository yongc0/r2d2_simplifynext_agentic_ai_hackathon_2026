"""Onboarding Agent — organisers' class: **Extraction** (Parse & Transform).

Conversational intake, not a form. Turns what somebody said about themselves
into a `Profile` and a `ConsentScope`.

The rule that matters, from docs/ARCHITECTURE.md §13.1:

    **Intent is never inferred from tone. If the user did not name it, it is
    not set.**

It is a safety rule, not a data-quality one. Reading "looking for something
casual" into a warm sentence, or "long term" into a serious one, puts people in
front of each other under a misunderstanding neither of them agreed to. So the
extraction returns intents only when a phrase names one, and when it cannot, it
says so in `unresolved` and the agent asks. `tests/test_intent.py` holds the
line with the tone-heavy sentences that most invite a guess.

Excluded by design: height, appearance, photographs. A product whose central
claim is removing judgement-by-photograph has nowhere to put them.
"""

from __future__ import annotations

import re

from src.agents.base import bounded_loop
from src.models import provider_available, structured_call
from src.safety.trust import TrustAndSafety
from src.schemas.agents import OnboardingExtraction
from src.schemas.core import (
    ConsentScope,
    Intent,
    Profile,
    TimeBucket,
    VerificationTier,
)
from src.telemetry.trace import set_attribute, span

AGENT_CLASS = "Extraction"

_SYSTEM = """You extract structure from what someone said about themselves \
during a conversational intake for Spark, a service that arranges one \
anonymous three-minute voice call a day.

Rules you must follow exactly:
- Set `intents` ONLY if the person named what they are looking for in words. \
Never infer intent from tone, warmth, seriousness or word choice. If they did \
not say, leave `intents` empty and add "intent" to `unresolved`.
- Never record height, appearance, body type or anything photographic. If they \
mention it, ignore it.
- `interests` and `values` must be things they actually said, in their words, \
lower-cased. Do not enrich, expand or infer.
- `availability_window` uses only: early_morning, morning, midday, afternoon, \
evening, night.
- `matchable_fields` lists only the fields they gave permission to use. If they \
said nothing about permission, include the fields they volunteered.

Use British spelling."""

#: Phrases that NAME an intent. Matching is deliberately literal — this list is
#: the specification of "the user said it", and anything not on it is not a
#: statement of intent no matter how strongly it hints.
_INTENT_PHRASES: tuple[tuple[str, Intent], ...] = (
    (r"\blong[- ]term\b", Intent.PARTNER_LONG_TERM),
    (r"\bsomething serious\b", Intent.PARTNER_LONG_TERM),
    (r"\bsettle down\b", Intent.PARTNER_LONG_TERM),
    (r"\blife partner\b", Intent.PARTNER_LONG_TERM),
    (r"\bmarriage\b", Intent.PARTNER_LONG_TERM),
    (r"\bshort[- ]term\b", Intent.PARTNER_SHORT_TERM),
    (r"\bcasual\b", Intent.PARTNER_SHORT_TERM),
    (r"\bnothing serious\b", Intent.PARTNER_SHORT_TERM),
    (r"\bsee where it goes\b", Intent.PARTNER_SHORT_TERM),
    (r"\b(?:make|meet|new) friends\b", Intent.FRIENDS),
    (r"\bfriendship\b", Intent.FRIENDS),
    (r"\bplatonic\b", Intent.FRIENDS),
)

_BUCKET_PHRASES: tuple[tuple[str, TimeBucket], ...] = (
    (r"\bearly morning|before work|dawn\b", TimeBucket.EARLY_MORNING),
    (r"\bmornings?\b", TimeBucket.MORNING),
    (r"\blunch|midday|noon\b", TimeBucket.MIDDAY),
    (r"\bafternoons?\b", TimeBucket.AFTERNOON),
    (r"\bevenings?|after work\b", TimeBucket.EVENING),
    (r"\bnights?|late\b", TimeBucket.NIGHT),
)

#: Physical attributes. Stripped whether a person volunteered them or a model
#: echoed them back — there is no field for them and there will not be one.
_EXCLUDED_ATTRIBUTES = re.compile(
    r"\b(?:height|tall|short|slim|fit|athletic|attractive|good[- ]looking|"
    r"pretty|handsome|photo|selfie|picture|body|weight|kg|cm)\b",
    re.I,
)


class OnboardingAgent:
    """Intake -> `Profile` + `ConsentScope`.

    The model does the reading; the intent rule is enforced afterwards in code
    (INVARIANT 6 in spirit: the thing that decides what someone is here for is
    not a probability distribution over their tone).
    """

    name = "onboarding"

    def __init__(self, trust: TrustAndSafety | None = None) -> None:
        self.trust = trust or TrustAndSafety()

    def extract(self, user_id: str, transcript: str) -> OnboardingExtraction:
        """Read an intake transcript into a validated extraction."""
        with span("agent.onboarding", user_id=user_id, chars=len(transcript)) as s:
            verdict = self.trust.screen_text(transcript, source="onboarding")
            if not verdict.allowed:
                s.set_attribute("blocked", ",".join(verdict.categories))
                # Screened intake still produces a structured result — the
                # person is told what happened by Trust & Safety, and the
                # extraction proceeds on nothing rather than on abuse.
                return OnboardingExtraction(unresolved=["intent", "interests"])

            extraction: OnboardingExtraction | None = None
            # Only enter the retry loop if there is a provider to retry. Looping
            # five times against a provider that is not configured is exactly
            # the circling that loop discipline (metric 3) is meant to catch.
            if provider_available():
                for _attempt in bounded_loop(self.name):
                    extraction = structured_call(
                        OnboardingExtraction,
                        role="fast",             # extraction is a fast-tier job
                        agent=self.name,
                        system=_SYSTEM,
                        user=transcript,
                    )
                    if extraction is not None:
                        break

            if extraction is None:
                extraction = self._deterministic_extract(transcript)
                s.set_attribute("source", "deterministic")
            else:
                s.set_attribute("source", "model")

            extraction = self._enforce_rules(extraction, transcript)
            s.set_attribute("intents", ",".join(i.value for i in extraction.intents))
            s.set_attribute("unresolved", ",".join(extraction.unresolved))
            return extraction

    # -----------------------------------------------------------------
    def _enforce_rules(
        self, extraction: OnboardingExtraction, transcript: str
    ) -> OnboardingExtraction:
        """The rules a model does not get a vote on.

        Intent survives only if the transcript names it. Physical attributes
        are stripped. Both apply to the deterministic path too, so the two
        paths cannot disagree about what a profile is allowed to contain.
        """
        named = _named_intents(transcript)
        kept = [i for i in extraction.intents if i in named]
        dropped = [i for i in extraction.intents if i not in named]
        if dropped:
            # The model read an intent into a transcript that never named one.
            # Recorded on the span so the rule is visibly doing work rather
            # than silently never firing.
            set_attribute(
                "onboarding.intents_dropped", ",".join(i.value for i in dropped)
            )

        unresolved = [u for u in extraction.unresolved if u != "intent"]
        if not kept:
            unresolved.append("intent")

        clean_interests = [i for i in extraction.interests if not _EXCLUDED_ATTRIBUTES.search(i)]
        clean_values = [v for v in extraction.values if not _EXCLUDED_ATTRIBUTES.search(v)]

        return extraction.model_copy(
            update={
                "intents": kept,
                "interests": clean_interests,
                "values": clean_values,
                "personality": _EXCLUDED_ATTRIBUTES.sub("", extraction.personality).strip(),
                "unresolved": sorted(set(unresolved)),
            }
        )

    def _deterministic_extract(self, transcript: str) -> OnboardingExtraction:
        """The no-model path.

        Keyword extraction, which is worse than a model at reading prose and
        exactly as good at the rule that matters. It exists so the system runs
        with no API key, and so a model outage during onboarding does not stop
        somebody signing up.
        """
        lowered = transcript.lower()
        interests = [term for term in _KNOWN_INTERESTS if re.search(rf"\b{term}\b", lowered)]
        values = [term for term in _KNOWN_VALUES if re.search(rf"\b{term}\b", lowered)]
        traits = [term for term in _KNOWN_TRAITS if re.search(rf"\b{term}\b", lowered)]
        buckets = [b for pattern, b in _BUCKET_PHRASES if re.search(pattern, lowered)]
        languages = [
            lang for lang in ("english", "mandarin", "malay", "tamil", "cantonese", "hokkien")
            if lang in lowered
        ]
        return OnboardingExtraction(
            intents=list(_named_intents(transcript)),
            interests=interests[:20],
            values=values[:10],
            personality=", ".join(traits[:5]),
            languages=languages or ["english"],
            availability_window=sorted(set(buckets), key=lambda b: b.value),
            matchable_fields=["intents", "languages", "availability_window", "interests"],
            unresolved=[],
        )

    # -----------------------------------------------------------------
    def to_profile(
        self,
        user_id: str,
        extraction: OnboardingExtraction,
        verification_tier: VerificationTier = VerificationTier.PHONE,
    ) -> tuple[Profile, ConsentScope]:
        """Turn a complete extraction into the durable objects.

        Refuses an extraction with no intent. That is the point of the rule: an
        unset intent is a question to ask, and a profile built on a guess is
        the harm the rule exists to prevent.
        """
        if not extraction.intents:
            raise ValueError(
                f"cannot build a profile for {user_id}: no intent was stated. "
                "Intent is never inferred (§13.1) — the Onboarding Agent must "
                "ask. `unresolved` says what to ask about: "
                f"{extraction.unresolved}"
            )
        profile = Profile(
            user_id=user_id,
            intents=extraction.intents,
            interests=extraction.interests,
            values=extraction.values,
            personality=extraction.personality,
            lifestyle=extraction.lifestyle,
            languages=extraction.languages or ["English"],
            availability_window=extraction.availability_window,
            dealbreakers=extraction.dealbreakers,
        )
        scope = ConsentScope(
            user_id=user_id,
            matchable_fields=extraction.matchable_fields
            or ["intents", "languages", "availability_window"],
        )
        return profile, scope

    def follow_up_question(self, extraction: OnboardingExtraction) -> str | None:
        """What to ask next. `None` when the intake is complete.

        Neutral by construction: the question offers all three options in a
        fixed order and volunteers none of them, because a question that leans
        is a way of inferring intent with extra steps.
        """
        if "intent" in extraction.unresolved:
            return (
                "Before we organise anything — what are you hoping to find here? "
                "Something long term, something short term, or friends? "
                "There is no wrong answer, and you can change it later."
            )
        if not extraction.availability_window:
            return "Which part of the day usually works best for you?"
        return None


def _named_intents(transcript: str) -> tuple[Intent, ...]:
    """The intents this text actually NAMES, in a stable order."""
    lowered = transcript.lower()
    found: list[Intent] = []
    for pattern, intent in _INTENT_PHRASES:
        if re.search(pattern, lowered) and intent not in found:
            found.append(intent)
    return tuple(found)


_KNOWN_INTERESTS = (
    "climbing", "running", "cooking", "film", "live music", "board games",
    "cycling", "photography", "reading", "hiking", "coffee", "pottery",
    "swimming", "languages", "volunteering", "gardening", "chess", "baking",
    "football", "yoga", "birdwatching", "woodwork",
)
_KNOWN_VALUES = (
    "honesty", "ambition", "family", "independence", "humour", "stability",
    "adventure", "kindness", "curiosity", "faith",
)
_KNOWN_TRAITS = (
    "outgoing", "thoughtful", "adventurous", "calm", "curious", "creative",
    "playful", "optimistic", "kind", "independent", "ambitious", "easygoing",
    "happy",
)
