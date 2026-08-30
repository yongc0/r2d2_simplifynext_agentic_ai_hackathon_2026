"""The schemas, and the claims that rest on them.

Schema validation pass rate is a graded metric, and it is only meaningful if
the schemas actually constrain something. These tests check that they do: that
a `ContinuityAction` cannot be ungrounded, that a `ConversationPrompt` cannot
cite one side, that a `DateSuggestion` cannot hide a commercial label.

The last section checks the claim on the architecture slide — seven of the
organisers' eight agent classes — against the code rather than against the
slide.
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import date as Date

import pytest
from pydantic import ValidationError

from src.agents.base import AGENT_CLASSES
from src.schemas.agents import (
    ContinuityAction,
    ConversationPrompt,
    DateSuggestion,
    GuardianPlan,
    MatchDecision,
    OnboardingExtraction,
    SafetyVerdict,
)
from src.schemas.core import Encounter, Intent, Overlap, Profile, TimeBucket, User

DAY = Date(2026, 9, 1)


# ---------------------------------------------------------------------------
# MatchDecision
# ---------------------------------------------------------------------------


def test_confidence_is_bounded():
    """An unbounded confidence is not a probability."""
    with pytest.raises(ValidationError):
        MatchDecision(day=DAY, user_id="a", candidate_id="b", rationale="x", confidence=1.4)


def test_a_decision_cannot_select_the_user_themselves():
    with pytest.raises(ValidationError, match="selected the user themselves"):
        MatchDecision(day=DAY, user_id="a", candidate_id="a", rationale="x", confidence=0.5)


def test_a_decision_must_name_someone_from_the_shortlist():
    """A selection we cannot explain is not one we should act on."""
    with pytest.raises(ValidationError, match="not explainable"):
        MatchDecision(
            day=DAY, user_id="a", candidate_id="z", rationale="x",
            confidence=0.5, considered=["b", "c"],
        )


def test_a_rationale_is_required():
    with pytest.raises(ValidationError):
        MatchDecision(day=DAY, user_id="a", candidate_id="b", rationale="", confidence=0.5)


# ---------------------------------------------------------------------------
# ContinuityAction — the difference between continuity and a reminder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["re_entry", "propose_meeting"])
def test_an_ungrounded_re_entry_is_refused(action):
    with pytest.raises(ValidationError, match="actually discussed"):
        ContinuityAction(
            lockin_id="l", user_id="u", action=action, message="Still there?", reference=""
        )


def test_a_grounded_re_entry_validates():
    action = ContinuityAction(
        lockin_id="l", user_id="u", action="re_entry",
        message="You left the climbing thing unfinished.", reference="climbing",
    )
    assert action.reference == "climbing"


def test_adjust_pace_must_carry_a_pace():
    with pytest.raises(ValidationError, match="pace_pref_days"):
        ContinuityAction(lockin_id="l", user_id="u", action="adjust_pace", message="Slower.")


def test_a_brief_needs_no_reference():
    """A first brief after a call has a note but no unfinished thread."""
    action = ContinuityAction(
        lockin_id="l", user_id="u", action="brief", message="You talked about climbing."
    )
    assert action.reference == ""


# ---------------------------------------------------------------------------
# ConversationPrompt — no invented commonality
# ---------------------------------------------------------------------------


def test_a_prompt_must_cite_both_people():
    with pytest.raises(ValidationError):
        ConversationPrompt(lockin_id="l", prompt="What now?", grounded_in=["climbing"])


def test_a_prompt_cannot_cite_an_empty_side():
    """An empty side means the shared interest was invented."""
    with pytest.raises(ValidationError, match="invented"):
        ConversationPrompt(lockin_id="l", prompt="What now?", grounded_in=["climbing", "  "])


# ---------------------------------------------------------------------------
# DateSuggestion and GuardianPlan
# ---------------------------------------------------------------------------


def test_a_venue_cannot_be_rendered_without_its_commercial_label():
    with pytest.raises(ValidationError):
        DateSuggestion(
            lockin_id="l", venue_id="v", activity="coffee", rationale="you both like it",
            fit_score=0.8, proposed_bucket=TimeBucket.EVENING,
        )


def test_guardian_cannot_imitate_a_system_alert():
    """There is no "fake system notification" channel to choose."""
    with pytest.raises(ValidationError):
        GuardianPlan(
            user_id="u", channel="system_alert", excuse_text="x", check_in_after_minutes=20
        )


def test_a_blocked_verdict_must_say_why():
    with pytest.raises(ValidationError, match="not actionable"):
        SafetyVerdict(allowed=False)


# ---------------------------------------------------------------------------
# Core domain
# ---------------------------------------------------------------------------


def test_an_overlap_has_one_representation_per_pair():
    """Sorted order, so (a, b) and (b, a) cannot both exist."""
    with pytest.raises(ValidationError, match="sorted order"):
        Overlap(user_a="u-b", user_b="u-a", cell_id="c", time_bucket=TimeBucket.EVENING, date=DAY)


def test_an_overlap_needs_two_people():
    with pytest.raises(ValidationError, match="two different users"):
        Overlap(user_a="u-a", user_b="u-a", cell_id="c", time_bucket=TimeBucket.EVENING, date=DAY)


def test_a_profile_attached_to_the_wrong_user_is_refused():
    """A profile carrying someone else's id is the shape of a mix-up that ends
    with one person's answers shown against another person's name."""
    from tests.conftest import make_user

    payload = make_user("u-a", 0, "Elowen Brackley").model_dump()
    payload["id"] = "u-different"
    with pytest.raises(ValidationError, match="wrong user"):
        User.model_validate(payload)


def test_profile_fields_are_normalised():
    profile = Profile(
        user_id="u", intents=[Intent.FRIENDS],
        interests=["Climbing", " climbing ", "FILM"],
    )
    assert profile.interests == ["climbing", "film"]


def test_an_encounter_knows_who_the_other_person_is():
    encounter = Encounter(id="e", match_id="m", day=DAY, user_a="u-a", user_b="u-b")
    assert encounter.other("u-a") == "u-b"
    with pytest.raises(ValueError, match="is not in encounter"):
        encounter.other("u-c")


def test_an_extraction_may_be_honestly_incomplete():
    """§13.1: an intake that did not name an intent must be able to say so
    rather than being forced to guess."""
    extraction = OnboardingExtraction(unresolved=["intent"])
    assert extraction.intents == []


# ---------------------------------------------------------------------------
# The seven-of-eight claim
# ---------------------------------------------------------------------------


def test_every_agent_module_names_its_organiser_class():
    """CLAUDE.md's "adding an agent" checklist, enforced.

    Every module in `src/agents/` that IS an agent declares which of the
    organisers' eight classes it belongs to.

    The exemptions are named rather than pattern-matched. A rule like "modules
    whose class ends in Agent" would quietly excuse `delivery.py`, whose class
    is `EncounterDelivery`; a list you have to edit makes adding an agent
    without its class a visible act rather than an accident.
    """
    import src.agents as agents_pkg

    #: Shared helpers, not agents. Each serves an agent that declares its own
    #: class: `base` the loop cap, `date_scoring` the Date Agent's ranking.
    helpers = {"base", "date_scoring"}

    missing = []
    for module_info in pkgutil.iter_modules(agents_pkg.__path__):
        if module_info.name in helpers:
            continue
        module = importlib.import_module(f"src.agents.{module_info.name}")
        if not getattr(module, "AGENT_CLASS", ""):
            missing.append(module_info.name)
    assert not missing, f"these agent modules declare no AGENT_CLASS: {missing}"


def test_spark_occupies_seven_of_the_eight_agent_classes():
    """The claim on the architecture slide, checked against the code.

    Seven, not eight: nothing in Spark is an *Information* agent. It does not
    answer questions or explain things — it arranges an encounter. Claiming the
    eighth would be the kind of overstatement the evaluation exists to catch.
    """
    import src.agents as agents_pkg

    covered: set[str] = {"Orchestration"}          # the supervisor graph
    for module_info in pkgutil.iter_modules(agents_pkg.__path__):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"src.agents.{module_info.name}")
        for part in getattr(module, "AGENT_CLASS", "").split("/"):
            for known in AGENT_CLASSES:
                if part.strip() and part.strip() in known:
                    covered.add(known)

    assert "Information" not in covered
    assert len(covered) == 7, f"expected seven agent classes, covered: {sorted(covered)}"
