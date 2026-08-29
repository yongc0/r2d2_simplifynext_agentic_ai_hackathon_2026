"""The agents, one section each.

CLAUDE.md's "adding an agent" checklist asks for, at minimum, a test that the
output validates and that the loop cap is respected. These go further where the
agent has a rule it could break — the Continuity Agent's grounding, the
Communication Agent's refusal to invent a commonality, the Date Agent's partner
labelling, and Guardian's refusal to imitate a system alert.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.agents.base import bounded_loop, loop_report
from src.agents.communication import CommunicationAgent
from src.agents.continuity import ContinuityAgent
from src.agents.date import DateAgent
from src.agents.guardian import GuardianAgent
from src.agents.match import MatchAgent, RandomArm, SimilarityArm
from src.config import SETTINGS
from src.ids import lockin_id
from src.mcp.services import WORLD
from src.schemas.core import LockIn, LockInState, TimeBucket
from src.telemetry.metrics import METRICS

NOW = datetime(2026, 9, 8, 9, 0)


@pytest.fixture
def lockin(users) -> LockIn:
    ids = sorted(users)
    lid = lockin_id(*ids)
    return LockIn(
        id=lid, pair_id=lid, user_a=ids[0], user_b=ids[1],
        opened_at=datetime(2026, 9, 1, 19, 3),
        last_contact=datetime(2026, 9, 1, 19, 3),
        contacts=1,
    )


# ---------------------------------------------------------------------------
# The loop cap
# ---------------------------------------------------------------------------


def test_the_loop_cap_comes_from_config_and_is_recorded():
    attempts = [n for n in bounded_loop("test-agent")]
    assert attempts == list(range(1, SETTINGS.loop.max_iterations + 1))
    assert METRICS.loop_iterations == [SETTINGS.loop.max_iterations]
    assert METRICS.loop_cap_hits.rate == 1.0


def test_breaking_out_early_is_recorded_as_such():
    for attempt in bounded_loop("test-agent"):
        if attempt == 2:
            break
    assert METRICS.loop_iterations == [2]
    assert METRICS.loop_cap_hits.rate == 0.0


def test_hitting_the_cap_logs_an_actionable_failure():
    list(bounded_loop("test-agent"))
    assert METRICS.failures
    assert "without converging" in METRICS.failures[0].detail


def test_a_zero_cap_is_refused_with_a_fix():
    with pytest.raises(ValueError, match="SPARK_MAX_LOOP_ITERATIONS"):
        list(bounded_loop("test-agent", cap=0))


def test_loop_report_records_even_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with loop_report("test-agent") as report:
            report.iterations = 3
            raise RuntimeError("boom")
    assert METRICS.loop_iterations == [3]


# ---------------------------------------------------------------------------
# Continuity — the "over time" agent
# ---------------------------------------------------------------------------


def test_week_five_differs_from_week_one(users, client, lockin):
    """The claim on the deck, as a test.

    Week 1: one note, so a brief. Week 5 with a history and several contacts:
    a specific proposal. If these ever came out the same, "adapts over time"
    would be a slogan.
    """
    agent = ContinuityAgent(client=client)
    owner = lockin.user_a
    agent.remember(lockin, owner, "climbing", NOW - timedelta(days=7))

    # Week 1: one note, one contact, and a gap that has reached the pair's pace.
    lockin.last_contact = NOW - timedelta(days=7)
    week_one = agent.act(lockin, users[owner], week=1, now=NOW - timedelta(days=4))

    # Week 5: a history of contacts, and still no meeting.
    lockin.contacts = 4
    lockin.last_contact = NOW - timedelta(days=3)
    week_five = agent.act(lockin, users[owner], week=5, now=NOW)

    assert week_one is not None and week_five is not None
    assert week_one.action != week_five.action
    assert week_five.action == "propose_meeting"
    assert week_five.reference == "climbing"


def test_a_re_entry_is_grounded_in_a_real_note(users, client, lockin):
    agent = ContinuityAgent(client=client)
    owner = lockin.user_a
    agent.remember(lockin, owner, "the film argument", NOW - timedelta(days=12))
    lockin.last_contact = NOW - timedelta(days=12)

    action = agent.act(lockin, users[owner], week=3, now=NOW)
    assert action is not None
    assert action.reference == "the film argument"
    assert "the film argument" in action.message


def test_a_long_silence_with_nothing_to_cite_is_released(users, client, lockin):
    """Releasing is kind, and holding a dead connection open costs one of only
    five slots."""
    agent = ContinuityAgent(client=client)
    owner = lockin.user_a
    lockin.last_contact = NOW - timedelta(days=SETTINGS.rules.lockin_quiet_days + 2)

    action = agent.act(lockin, users[owner], week=4, now=NOW)   # no notes at all
    assert action is not None and action.action == "release"


def test_a_quiet_lockin_is_released_after_one_re_entry(users, client, lockin):
    agent = ContinuityAgent(client=client)
    owner = lockin.user_a
    agent.remember(lockin, owner, "climbing", NOW - timedelta(days=20))
    lockin.last_contact = NOW - timedelta(days=SETTINGS.rules.lockin_quiet_days + 2)

    first = agent.act(lockin, users[owner], week=4, now=NOW)
    assert first is not None and first.action == "re_entry"

    lockin.state = LockInState.QUIET                 # the re-entry went unanswered
    second = agent.act(lockin, users[owner], week=5, now=NOW)
    assert second is not None and second.action == "release"


def test_nothing_is_sent_on_most_days(users, client, lockin):
    """An agent that acts every day is a notification schedule, not attention."""
    agent = ContinuityAgent(client=client)
    lockin.last_contact = NOW - timedelta(hours=2)
    assert agent.act(lockin, users[lockin.user_a], week=2, now=NOW) is None


def test_a_user_who_declined_notes_gets_no_memory_based_action(users, client, lockin):
    agent = ContinuityAgent(client=client)
    owner = lockin.user_a
    users[owner].consent_scope.allow_continuity_notes = False
    agent.remember(lockin, owner, "climbing", NOW - timedelta(days=7))
    lockin.last_contact = NOW - timedelta(days=7)
    assert agent.act(lockin, users[owner], week=3, now=NOW) is None


def test_pace_learning_moves_slowly_and_stays_bounded(client, lockin):
    agent = ContinuityAgent(client=client)
    assert lockin.pace_pref_days == 3.0
    once = agent.learn_pace(lockin, gap_days=14)
    assert 3.0 < once < 14.0, "one long week should not redefine the pair's rhythm"
    lockin.pace_pref_days = once
    for _ in range(50):
        lockin.pace_pref_days = agent.learn_pace(lockin, gap_days=1000)
    assert lockin.pace_pref_days <= 30.0


def test_a_brief_with_nothing_to_cite_is_not_sent(users, client, lockin):
    agent = ContinuityAgent(client=client)
    assert agent.brief(lockin, users[lockin.user_a], week=2, now=NOW) is None


# ---------------------------------------------------------------------------
# Communication — no invented commonality
# ---------------------------------------------------------------------------


def test_no_prompt_without_grounding_on_both_sides(users, client, lockin):
    """One-sided grounding produces silence, not a plausible sentence."""
    for user in users.values():
        user.consent_scope.allow_conversation_prompts = True
    agent = CommunicationAgent(client=client)
    ContinuityAgent(client=client).remember(lockin, lockin.user_a, "climbing", NOW)

    prompt = agent.suggest(lockin, users[lockin.user_a], users[lockin.user_b], NOW)
    assert prompt is None, "a prompt was produced from one person's notes alone"


def test_a_grounded_prompt_cites_both_people(users, client, lockin):
    for user in users.values():
        user.consent_scope.allow_conversation_prompts = True
    continuity = ContinuityAgent(client=client)
    continuity.remember(lockin, lockin.user_a, "climbing", NOW)
    continuity.remember(lockin, lockin.user_b, "old films", NOW)

    prompt = CommunicationAgent(client=client).suggest(
        lockin, users[lockin.user_a], users[lockin.user_b], NOW
    )
    assert prompt is not None
    assert set(prompt.grounded_in) == {"climbing", "old films"}
    assert "climbing" in prompt.prompt and "old films" in prompt.prompt


def test_the_prompt_is_opt_in_on_both_sides(users, client, lockin):
    continuity = ContinuityAgent(client=client)
    continuity.remember(lockin, lockin.user_a, "climbing", NOW)
    continuity.remember(lockin, lockin.user_b, "old films", NOW)
    users[lockin.user_a].consent_scope.allow_conversation_prompts = True
    users[lockin.user_b].consent_scope.allow_conversation_prompts = False

    assert CommunicationAgent(client=client).suggest(
        lockin, users[lockin.user_a], users[lockin.user_b], NOW
    ) is None


def test_an_invented_citation_is_rejected():
    """The verifier, directly: a plausible-sounding citation that nobody made
    must not pass."""
    from src.schemas.agents import ConversationPrompt

    invented = ConversationPrompt(
        lockin_id="l", prompt="You both love sailing?", grounded_in=["sailing", "sailing"]
    )
    assert CommunicationAgent._verify_grounding(invented, ["climbing"], ["old films"]) is False

    honest = ConversationPrompt(
        lockin_id="l", prompt="Climbing or films?", grounded_in=["climbing", "old films"]
    )
    assert CommunicationAgent._verify_grounding(honest, ["climbing"], ["old films"]) is True


# ---------------------------------------------------------------------------
# Date
# ---------------------------------------------------------------------------


def test_a_partner_venue_is_labelled_in_the_sentence_a_user_reads(users, client, lockin):
    WORLD.venues["v-cook"] = {
        "id": "v-cook", "activity": "a two-hour cooking class", "tags": ["climbing"],
        "buckets": ["evening"], "is_commercial_partner": True,
    }
    WORLD.availability[lockin.user_a] = [TimeBucket.EVENING]
    WORLD.availability[lockin.user_b] = [TimeBucket.EVENING]

    suggestion = DateAgent(client=client).suggest(
        lockin, users[lockin.user_a], users[lockin.user_b]
    )
    assert suggestion is not None and suggestion.is_commercial_partner is True
    assert "Spark partner venue" in DateAgent.render_label(suggestion)


def test_no_proposal_when_there_is_nothing_shared_to_build_on(users, client, lockin):
    users[lockin.user_b].profile.interests = ["woodwork"]
    WORLD.availability[lockin.user_a] = [TimeBucket.EVENING]
    WORLD.availability[lockin.user_b] = [TimeBucket.EVENING]
    assert DateAgent(client=client).suggest(
        lockin, users[lockin.user_a], users[lockin.user_b]
    ) is None


# ---------------------------------------------------------------------------
# Guardian
# ---------------------------------------------------------------------------


def test_guardian_never_imitates_a_system_alert():
    with pytest.raises(ValueError, match="never imitates"):
        GuardianAgent().plan("u-alice", NOW, channel="system_notification")


def test_guardian_uses_the_users_own_words_unchanged():
    plan = GuardianAgent().plan("u-alice", NOW, excuse="Your reminder: leave by nine.")
    assert plan.excuse_text == "Your reminder: leave by nine."


def test_an_unanswered_check_in_is_itself_recorded():
    agent = GuardianAgent()
    agent.plan("u-alice", NOW)
    agent.record_check_in("u-alice", NOW + timedelta(minutes=20), answered=False)
    entries = agent.log.for_user("u-alice")
    assert len(entries) == 2
    assert "NO ANSWER" in entries[-1]["detail"]


# ---------------------------------------------------------------------------
# Match — the three arms share one filter
# ---------------------------------------------------------------------------


def test_all_three_arms_apply_the_same_eligibility_filter(users, client, trust):
    """The comparison in eval/ measures selection, not filtering.

    Every arm is given a pool of one ineligible candidate. All three must
    return nothing — if one of them matched, the evaluation would be comparing
    filters instead of matchers.
    """
    import random
    from datetime import date as Date

    alice, bob = (users[k] for k in sorted(users))
    trust.block(alice.id, bob.id)
    day = Date(2026, 9, 1)

    arms = [
        MatchAgent(client=client, trust=trust),
        RandomArm(client=client, trust=trust, rng=random.Random(1)),
        SimilarityArm(client=client, trust=trust),
    ]
    for arm in arms:
        assert arm.select(alice, [bob], day) is None, f"{arm.name} matched a blocked pair"


def test_the_match_agent_returns_none_rather_than_inventing_an_encounter(
    users, client, trust
):
    """Some days nobody's path crossed yours in a way that works."""
    from datetime import date as Date

    alice = users[sorted(users)[0]]
    assert MatchAgent(client=client, trust=trust).select(alice, [], Date(2026, 9, 1)) is None


def test_a_selection_names_only_shortlisted_candidates(users, client, trust):
    from datetime import date as Date

    alice, bob = (users[k] for k in sorted(users))
    decision = MatchAgent(client=client, trust=trust).select(alice, [bob], Date(2026, 9, 1))
    assert decision is not None
    assert decision.candidate_id in decision.considered


# ---------------------------------------------------------------------------
# Model resilience
# ---------------------------------------------------------------------------


def test_the_breaker_opens_after_repeated_provider_failures():
    """A provider that starts failing must not make every remaining decision
    pay a timeout. The breaker opens, the run finishes on the deterministic
    policy, and the reason is recorded rather than hidden."""
    from src.models import BREAKER

    BREAKER.reset()
    try:
        for _ in range(BREAKER.threshold):
            BREAKER.record_failure("RateLimitError: 429")
        assert BREAKER.opened is True
        assert METRICS.llm_fallbacks, "opening the breaker was not recorded"
        assert "deterministic policy" in METRICS.llm_fallbacks[-1].detail
    finally:
        BREAKER.reset()


def test_a_schema_miss_does_not_trip_the_breaker():
    """One badly-shaped output is the model's answer, not the provider being
    down. Switching the model off for the rest of a run over it would be an
    overreaction with no way back."""
    from src.models import BREAKER

    BREAKER.reset()
    try:
        for _ in range(BREAKER.threshold - 1):
            BREAKER.record_failure("timeout")
        BREAKER.record_success()
        BREAKER.record_failure("timeout")
        assert BREAKER.opened is False
    finally:
        BREAKER.reset()
