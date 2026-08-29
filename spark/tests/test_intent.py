"""Eligibility rules, and the one rule the Onboarding Agent must not break.

§13.1: **intent is never inferred from tone. If the user did not name it, it is
not set.** The tone-heavy sentences below are the ones that most invite a
guess, and a system that guesses puts two people in front of each other under a
misunderstanding neither agreed to.
"""

from __future__ import annotations

from datetime import date as Date

import pytest

from src.agents.match import eligible, intents_compatible, permitted_overlap
from src.agents.onboarding import OnboardingAgent
from src.schemas.core import Intent, TimeBucket
from tests.conftest import make_user

DAY = Date(2026, 9, 1)


# ---------------------------------------------------------------------------
# Intent is never inferred
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transcript",
    [
        "I've been on the apps for years and I'm tired of it.",
        "I just want to meet someone I actually like, you know?",
        "Honestly I'm not sure what I'm looking for.",
        "I'm quite serious as a person, I don't mess about.",       # tone, not intent
        "I'm pretty relaxed and easy-going about most things.",     # tone, not intent
        "My last relationship ended badly.",
        "I like climbing and old films.",
    ],
)
def test_intent_is_never_inferred_from_tone(transcript):
    """None of these NAMES an intent, so none of them may set one."""
    agent = OnboardingAgent()
    extraction = agent.extract("u-test", transcript)
    assert extraction.intents == [], (
        f"an intent was inferred from {transcript!r}. §13.1: if the user did "
        "not name it, it is not set."
    )
    assert "intent" in extraction.unresolved


@pytest.mark.parametrize(
    "transcript,expected",
    [
        ("I'm looking for something long-term.", Intent.PARTNER_LONG_TERM),
        ("Honestly I want to settle down.", Intent.PARTNER_LONG_TERM),
        ("Something casual, nothing heavy.", Intent.PARTNER_SHORT_TERM),
        ("I just want to make friends here.", Intent.FRIENDS),
        ("Strictly platonic for me.", Intent.FRIENDS),
    ],
)
def test_a_named_intent_is_kept(transcript, expected):
    extraction = OnboardingAgent().extract("u-test", transcript)
    assert expected in extraction.intents
    assert "intent" not in extraction.unresolved


def test_the_follow_up_question_offers_every_option_neutrally():
    """A question that leans is inference with extra steps."""
    extraction = OnboardingAgent().extract("u-test", "I like hiking.")
    question = OnboardingAgent().follow_up_question(extraction)
    assert question is not None
    lowered = question.lower()
    for option in ("long term", "short term", "friends"):
        assert option in lowered


def test_a_profile_cannot_be_built_without_a_stated_intent():
    agent = OnboardingAgent()
    extraction = agent.extract("u-test", "I like hiking and old films.")
    with pytest.raises(ValueError, match="no intent was stated"):
        agent.to_profile("u-test", extraction)


# ---------------------------------------------------------------------------
# Appearance is excluded by design
# ---------------------------------------------------------------------------


def test_physical_attributes_are_stripped():
    """The product's central claim is removing judgement-by-photograph, so
    there is nowhere for these to go — even when volunteered."""
    extraction = OnboardingAgent().extract(
        "u-test",
        "I'm looking for something long-term. I'm tall and quite athletic, "
        "and I like climbing.",
    )
    joined = " ".join(extraction.interests + extraction.values + [extraction.personality])
    for word in ("tall", "athletic", "height"):
        assert word not in joined.lower()
    assert "climbing" in extraction.interests


def test_the_profile_schema_has_no_appearance_field():
    from src.schemas.core import Profile

    forbidden = {"height", "appearance", "photo", "photos", "body_type", "build"}
    assert forbidden.isdisjoint(Profile.model_fields)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_intent_is_a_hard_filter_not_a_similarity_score():
    """Friends and short-term is not a 33% match; it is a misunderstanding."""
    assert intents_compatible([Intent.FRIENDS], [Intent.PARTNER_SHORT_TERM]) is False
    assert intents_compatible([Intent.FRIENDS], [Intent.FRIENDS]) is True
    assert (
        intents_compatible(
            [Intent.FRIENDS, Intent.PARTNER_LONG_TERM], [Intent.PARTNER_LONG_TERM]
        )
        is True
    )


def test_no_shared_language_is_ineligible(trust):
    a = make_user("u-a", 0, "Elowen Brackley", languages=["English"])
    b = make_user("u-b", 1, "Torin Kilbride", languages=["Tamil"])
    why_not = eligible(a, b, DAY, trust, 5)
    assert why_not is not None and "language" in why_not.reason


def test_never_free_at_the_same_time_is_ineligible(trust):
    a = make_user("u-a", 0, "Elowen Brackley", buckets=[TimeBucket.MORNING])
    b = make_user("u-b", 1, "Torin Kilbride", buckets=[TimeBucket.NIGHT])
    why_not = eligible(a, b, DAY, trust, 5)
    assert why_not is not None and "same time" in why_not.reason


def test_a_block_works_in_both_directions(trust):
    """A one-way block that still surfaces the blocker to the blocked person is
    not a block."""
    a = make_user("u-a", 0, "Elowen Brackley")
    b = make_user("u-b", 1, "Torin Kilbride")
    trust.block(b.id, a.id)                       # B blocked A; A never blocked B
    assert eligible(a, b, DAY, trust, 5) is not None
    assert eligible(b, a, DAY, trust, 5) is not None


def test_cooldown_prevents_an_immediate_rematch(trust):
    a = make_user("u-a", 0, "Elowen Brackley")
    b = make_user("u-b", 1, "Torin Kilbride")
    trust.note_match(a.id, b.id, DAY)
    assert eligible(a, b, DAY, trust, 5) is not None
    later = Date.fromordinal(DAY.toordinal() + 400)
    assert eligible(a, b, later, trust, 5) is None


def test_no_lockin_slot_is_ineligible(trust):
    a = make_user("u-a", 0, "Elowen Brackley")
    b = make_user("u-b", 1, "Torin Kilbride")
    b.lockin_slots = 0
    why_not = eligible(a, b, DAY, trust, 5)
    assert why_not is not None and "slot" in why_not.reason


def test_a_user_is_never_their_own_encounter(trust):
    a = make_user("u-a", 0, "Elowen Brackley")
    assert eligible(a, a, DAY, trust, 5) is not None


def test_a_dealbreaker_is_matched_against_what_was_volunteered(trust):
    a = make_user("u-a", 0, "Elowen Brackley")
    b = make_user("u-b", 1, "Torin Kilbride", interests=["climbing", "smoking"])
    a.profile.dealbreakers = ["smoking"]
    why_not = eligible(a, b, DAY, trust, 5)
    assert why_not is not None and "dealbreaker" in why_not.reason


# ---------------------------------------------------------------------------
# Consent scope
# ---------------------------------------------------------------------------


def test_a_withheld_field_cannot_influence_a_match():
    """`ConsentScope.matchable_fields` is not advisory.

    A field the user withheld may not influence a selection even though it sits
    on their profile.
    """
    a = make_user("u-a", 0, "Elowen Brackley", interests=["climbing", "film"])
    b = make_user("u-b", 1, "Torin Kilbride", interests=["climbing", "film"])
    assert permitted_overlap(a, b, "interests") == {"climbing", "film"}

    b.consent_scope.matchable_fields = ["intents", "languages"]      # interests withheld
    assert permitted_overlap(a, b, "interests") == set()
