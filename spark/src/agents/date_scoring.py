"""How Date Studio ranks, and how it explains itself.

Lifted out of `DateAgent` so the ordering can be tested on its own, without a
world, a lock-in or an MCP client. The scorer is the part that has to be
defensible, and a function you can call with a dict is easier to hold to that
than a method reachable only through four layers of setup.

THE RULE THIS FILE EXISTS TO ENFORCE

Evidence first, sentence second. `explain()` is built FROM the terms that
actually scored, so a rationale cannot describe a reason the ranking did not
use. Writing the explanation first and finding support for it afterwards is how
recommenders end up confidently describing preferences nobody has — and it is
indistinguishable, from the outside, from personalisation that works.

Deterministic throughout. No randomness, no clock, no model call: the same
inputs produce the same order, because a demo that ranks differently between
takes cannot be filmed twice and a ranking nobody can reproduce cannot be
audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.schemas.date_studio import (
    REASON_TO_DIMENSION,
    DateMemoryItem,
    DatePlanFeedback,
    DatePlanningPreferences,
)

# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
#
# Named constants rather than literals inside an expression, so the priority
# order is legible here rather than reconstructed from arithmetic.

#: What they asked for THIS TIME. The largest term by a distance: a stated
#: constraint is not a hint, and a recommender that lets last month's inferred
#: preference outrank tonight's explicit choice is not personalising, it is
#: arguing.
_W_REQUEST = 1.0

#: What Spark remembers, scaled by confidence — so an explicit preference (1.0)
#: weighs five times an inference at the 0.2 a single signal earns.
_W_MEMORY = 0.5

#: A small nudge toward shapes this pair have saved before.
_W_SAVED = 0.25

#: Subtracted for a dimension this pair explicitly rejected here. Deliberately
#: smaller than `_W_REQUEST`: one rejection should move the order, not delete an
#: option from the world.
_W_REJECTED = 0.4

#: Subtracted for a lead venue already shown to this pair. Stops the same
#: evening arriving three weeks running.
_W_REPEAT = 0.6

#: Every path must clear this after scoring. Without it a "match" of nothing but
#: penalties could still rank third and be offered as a suggestion.
MIN_SCORE = 0.0


@dataclass
class ScoreBreakdown:
    """Every term that moved the number, kept for the explanation.

    The breakdown is the evidence, and `explain()` may only speak from it. That
    is the whole mechanism keeping the rationale honest.
    """

    total: float = 0.0
    #: (dimension, value) the request asked for and this venue satisfies.
    request_hits: list[tuple[str, str]] = field(default_factory=list)
    #: (dimension, value, confidence) from durable memory.
    memory_hits: list[tuple[str, str, float]] = field(default_factory=list)
    #: Shared interests this path is actually built on.
    shared_interests: list[str] = field(default_factory=list)
    saved_shape: bool = False
    rejected_dimensions: list[str] = field(default_factory=list)
    repeated_lead: bool = False


def score_candidate(
    *,
    venue: dict,
    shared_interests: list[str],
    preferences: DatePlanningPreferences,
    memory: list[DateMemoryItem],
    feedback: list[DatePlanFeedback],
    seen_leads: set[str],
    saved_shapes: set[str],
    shape: str,
) -> ScoreBreakdown:
    """Rank one candidate lead venue for one pair.

    The order of the terms is the order of the argument: what you asked for,
    then what we remember, then what you have liked, then what you have turned
    down, then whether you have seen it already.
    """
    breakdown = ScoreBreakdown()

    # --- 1. the interests both people actually listed --------------------
    tags = {t.lower() for t in venue.get("tags", ())}
    breakdown.shared_interests = sorted(tags & {i.lower() for i in shared_interests})

    # --- 2. this request --------------------------------------------------
    for dimension, value in preferences.as_pairs():
        if _venue_matches(venue, dimension, value):
            breakdown.request_hits.append((dimension, value))
            breakdown.total += _W_REQUEST

    # --- 3. durable memory -------------------------------------------------
    # Skipped where the request already spoke: someone who chose "under $20"
    # tonight has overridden what we remember, and counting both would let
    # memory quietly double a preference they had already stated.
    stated = {dimension for dimension, _ in preferences.as_pairs()}
    for item in memory:
        if item.dimension in stated:
            continue
        if _venue_matches(venue, item.dimension, item.value):
            breakdown.memory_hits.append(
                (item.dimension, item.value, item.confidence)
            )
            breakdown.total += _W_MEMORY * item.confidence

    # --- 4. shapes they have saved before ----------------------------------
    if shape in saved_shapes:
        breakdown.saved_shape = True
        breakdown.total += _W_SAVED

    # --- 5. what they turned down, for THIS connection ---------------------
    for dimension in _rejected_dimensions(feedback):
        if dimension == "format" and venue.get("format") == "event":
            breakdown.rejected_dimensions.append("too_crowded")
            breakdown.total -= _W_REJECTED
        elif dimension == "budget" and venue.get("budget") in ("under_50",):
            breakdown.rejected_dimensions.append("too_expensive")
            breakdown.total -= _W_REJECTED
        elif dimension == "duration" and venue.get("duration") == "whole_evening":
            breakdown.rejected_dimensions.append("too_long")
            breakdown.total -= _W_REJECTED
        elif dimension == "energy" and venue.get("energy") == "high":
            breakdown.rejected_dimensions.append("too_active")
            breakdown.total -= _W_REJECTED

    # --- 6. do not offer the same evening again ----------------------------
    if venue.get("venue_id") in seen_leads:
        breakdown.repeated_lead = True
        breakdown.total -= _W_REPEAT

    return breakdown


def _venue_matches(venue: dict, dimension: str, value: str) -> bool:
    """Whether a venue satisfies one (dimension, value).

    `flexible` budget matches anything: it is the absence of a constraint, not a
    band a venue could sit in.
    """
    if dimension == "budget":
        return value == "flexible" or venue.get("budget") == value
    if dimension == "duration":
        return venue.get("duration") == value
    if dimension == "energy":
        return venue.get("energy") == value
    if dimension == "format":
        return venue.get("format") == value
    if dimension == "mood":
        return venue.get("energy") in _MOOD_ENERGY.get(value, ())
    return False


#: Mood is the one dimension with no venue field of its own, so it is expressed
#: through energy rather than invented as a separate attribute. Stated here
#: rather than hidden in the scorer, because it IS an interpretation and a
#: reader should be able to disagree with it.
_MOOD_ENERGY: dict[str, tuple[str, ...]] = {
    "easy": ("low",),
    "meaningful": ("low", "medium"),
    "playful": ("medium", "high"),
    "adventurous": ("high",),
}


def _rejected_dimensions(feedback: list[DatePlanFeedback]) -> list[str]:
    """Dimensions this pair have rejected, from active feedback only.

    `not_our_style` and `already_done` map to nothing on purpose: neither says
    WHICH dimension was wrong, and turning a shrug into a budget preference is
    exactly the invention this file exists to prevent. Repetition is handled by
    the seen-leads penalty instead.
    """
    dimensions: list[str] = []
    for entry in feedback:
        if entry.action != "rejected":
            continue
        for reason in entry.reasons:
            mapped = REASON_TO_DIMENSION.get(reason)
            if mapped and mapped[0] not in dimensions:
                dimensions.append(mapped[0])
    return dimensions


# ---------------------------------------------------------------------------
# The explanation
# ---------------------------------------------------------------------------


def explain(breakdown: ScoreBreakdown, bucket: str) -> str:
    """A rationale assembled from the terms that actually scored.

    Nothing is added here that the scorer did not use. If a clause appears in
    this sentence, the number moved because of it — which is what makes "why
    this fits you" checkable rather than decorative.
    """
    parts: list[str] = []

    if breakdown.shared_interests:
        interests = _join(breakdown.shared_interests[:2])
        parts.append(f"you have both mentioned {interests}")

    if breakdown.request_hits:
        asked = _join([_phrase(d, v) for d, v in breakdown.request_hits[:2]])
        parts.append(f"you asked for {asked}")

    if breakdown.memory_hits:
        # Highest confidence first — the strongest thing we know, not the first
        # thing we happened to store.
        best = max(breakdown.memory_hits, key=lambda hit: hit[2])
        parts.append(f"you usually prefer {_phrase(best[0], best[1])}")

    if breakdown.saved_shape:
        parts.append("it is the kind of plan you have saved before")

    if not parts:
        # No evidence, no sentence. A path with nothing to cite is not built,
        # so this is a guard rather than a fallback.
        return ""

    # Two sentences, and the clauses joined with commas rather than "and".
    # Several clauses contain their own "and" ("reading and coffee", "something
    # free and something relaxed"), and joining those with another one produced
    # a sentence that read like a list of lists.
    readable_bucket = bucket.replace("_", " ")
    evidence = ", ".join(parts)
    return f"You are both free in the {readable_bucket}. {evidence[0].upper()}{evidence[1:]}."


def _phrase(dimension: str, value: str) -> str:
    """One (dimension, value) in words. British spelling, per CLAUDE.md."""
    return {
        "budget": {
            "free": "something free",
            "under_20": "something under $20",
            "under_50": "something under $50",
            "flexible": "no particular budget",
        },
        "duration": {
            "one_hour": "about an hour",
            "two_hours": "a couple of hours",
            "whole_evening": "a whole evening",
        },
        "energy": {
            "low": "something relaxed",
            "medium": "something in between",
            "high": "something active",
        },
        "mood": {
            "easy": "an easy one",
            "playful": "something playful",
            "adventurous": "something adventurous",
            "meaningful": "something with a bit of depth",
        },
        "format": {
            "food": "somewhere to eat",
            "activity": "something to do",
            "outdoors": "being outdoors",
            "learning": "learning something",
            "event": "an event",
        },
    }.get(dimension, {}).get(value, value.replace("_", " "))


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
