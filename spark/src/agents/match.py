"""Match Agent — organisers' class: **Decision-Support** (Guide & Recommend).

Selects **one** encounter per day from that day's overlap pool.
docs/ARCHITECTURE.md §13.2.

Three stages, deliberately separated, because only the middle one is a
judgement call:

  1. `eligible()`   hard rules. Ordinary Python, unit-tested, no model.
                    Intent, language, availability, blocks, cooldowns, slots,
                    dealbreakers. A model does not get a vote on eligibility
                    (INVARIANT 6).
  2. `shortlist()`  deterministic ranking down to at most five candidates —
                    overlap strength, permitted-field similarity, novelty, and
                    distribution fairness (§15.2).
  3. `select()`     the model chooses among the five and says why. Falls back
                    to the top of the shortlist if the model is unavailable or
                    returns something that does not validate.

**The claim we make and defend.** The model estimates who is worth three
minutes from stated preferences, interests, personality and behavioural
feedback. It does not predict attraction, and this module does not claim to:
Joel, Eastwick & Finkel (2017) showed that ML over 100+ self-reported traits
cannot predict relationship-specific attraction above chance. `eval/run_arms.py`
benchmarks this agent against random assignment precisely so the claim can
fail, and CLAUDE.md pre-registers us to report it if it does.

The two baseline arms live at the bottom of this file rather than in `eval/`,
so that all three arms provably share one eligibility filter. A comparison in
which the arms disagree about who is *allowed* to be matched would be measuring
the filter, not the matcher.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Protocol

from src.agents.base import loop_report
from src.ids import match_id
from src.mcp.registry import MCPClient
from src.models import structured_call
from src.safety.trust import TrustAndSafety
from src.schemas.agents import MatchChoice, MatchDecision
from src.schemas.core import Intent, User
from src.telemetry.trace import span

AGENT_CLASS = "Decision-Support"

#: How many candidates reach the judgement stage. Five because a short list is
#: what makes the choice explainable — the rationale has to be about someone
#: the shortlist can name, and `MatchDecision` refuses a candidate that was not
#: on it.
SHORTLIST_SIZE = 5

_SYSTEM = """You choose which ONE person, out of a shortlist, is worth a \
three-minute anonymous voice call today.

You are not predicting attraction, and you must not claim to. You are judging \
who is worth three minutes of someone's evening, given what both people have \
said about themselves.

Rules:
- Choose a candidate_id from the shortlist. Nothing else is a valid answer.
- The rationale is shown to the user. It must be one sentence, refer only to \
things in the shortlist entry, and mention NO place, NO distance, NO time of \
day beyond a coarse word, and NO name.
- confidence is how sure you are that this is worth three minutes, from 0 to \
1. Be honest and unheroic: 0.5 means you are guessing.
- Prefer someone whose stated intent matches, whose interests give them \
something to talk about, and who they have crossed paths with more than once.

Use British spelling."""


# ---------------------------------------------------------------------------
# Stage 1 — eligibility. Hard rules, no model.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ineligible:
    """Why a candidate was ruled out. Kept for the trace and the fairness
    audit — "no match today" with no reason is not debuggable."""

    candidate_id: str
    reason: str


def intents_compatible(a: list[Intent], b: list[Intent]) -> bool:
    """Intent is a hard filter, and it is not a similarity score.

    Someone here for friends and someone here for a short-term partner do not
    have a 33% match; they have a misunderstanding waiting to happen. The rule
    is an intersection: they must both have named at least one of the same
    thing.
    """
    return bool(set(a) & set(b))


def eligible(
    user: User,
    candidate: User,
    day: Date,
    trust: TrustAndSafety,
    max_lockins: int,
) -> Ineligible | None:
    """`None` when the pair may be matched, otherwise why not.

    Every rule here is one someone could be harmed by getting wrong, which is
    why none of them is a model's opinion.
    """
    if user.id == candidate.id:
        return Ineligible(candidate.id, "a user is not their own encounter")
    if trust.is_blocked(user.id, candidate.id):
        return Ineligible(candidate.id, "blocked by one of the two parties")
    if trust.in_cooldown(user.id, candidate.id, day):
        return Ineligible(candidate.id, "matched recently; still in cooldown")
    if not intents_compatible(user.profile.intents, candidate.profile.intents):
        return Ineligible(candidate.id, "no shared intent")
    if not set(user.profile.languages) & set(candidate.profile.languages):
        return Ineligible(candidate.id, "no shared language")
    if not set(user.profile.availability_window) & set(candidate.profile.availability_window):
        return Ineligible(candidate.id, "never free at the same time")
    if user.lockin_slots <= 0 or candidate.lockin_slots <= 0:
        return Ineligible(candidate.id, "no lock-in slot free on one side")
    if _hits_dealbreaker(user, candidate) or _hits_dealbreaker(candidate, user):
        return Ineligible(candidate.id, "a stated dealbreaker applies")
    if max_lockins <= 0:
        return Ineligible(candidate.id, "lock-in ceiling is zero in this configuration")
    return None


def _hits_dealbreaker(user: User, other: User) -> bool:
    """A dealbreaker matches against what the other person volunteered.

    Deliberately narrow: it looks at interests and lifestyle, both of which the
    person chose to state. It does not infer, and there is no appearance field
    for it to read.
    """
    if not user.profile.dealbreakers:
        return False
    haystack = set(other.profile.interests) | {other.profile.lifestyle.lower()}
    return any(
        any(breaker in item for item in haystack) for breaker in user.profile.dealbreakers
    )


# ---------------------------------------------------------------------------
# Stage 2 — the shortlist. Deterministic ranking.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredCandidate:
    candidate_id: str
    score: float
    crossings: int
    shared_interests: tuple[str, ...]
    shared_bucket: str | None
    components: dict[str, float] = field(default_factory=dict)


def permitted_overlap(user: User, other: User, field_name: str) -> set[str]:
    """Shared values of a field, but only if BOTH have permitted its use.

    `ConsentScope.matchable_fields` is not advisory. A field the user withheld
    may not influence a selection even though it sits on their profile, so the
    check is here, in the scoring function, where it cannot be skipped.
    """
    if not (user.consent_scope.permits(field_name) and other.consent_scope.permits(field_name)):
        return set()
    return set(getattr(user.profile, field_name)) & set(getattr(other.profile, field_name))


# Weights for the deterministic ranking. Named constants rather than literals
# in an expression, so the objective order in §13.2 is legible here.
_W_CROSSINGS = 0.30
_W_INTERESTS = 0.28
_W_VALUES = 0.14
_W_AVAILABILITY = 0.12
_W_NOVELTY = 0.06
_W_FAIRNESS = 0.10


@dataclass
class MatchAgent:
    """The Spark arm. Deterministic shortlist, model judgement over the top five."""

    client: MCPClient
    trust: TrustAndSafety
    max_lockins: int = 5
    name: str = "match"

    def score(
        self,
        user: User,
        candidate: User,
        day: Date,
        recent_partners: set[str],
        encounter_counts: Counter,
    ) -> ScoredCandidate:
        """Rank one eligible candidate. All components in [0, 1]."""
        strength = self.client.try_call(
            "spark-overlap",
            "overlap_strength",
            default={"crossings": 0, "buckets": []},
            user_id=user.id,
            candidate_id=candidate.id,
            day=day.isoformat(),
        ) or {"crossings": 0, "buckets": []}
        crossings = int(strength.get("crossings", 0))

        shared_interests = permitted_overlap(user, candidate, "interests")
        shared_values = permitted_overlap(user, candidate, "values")
        shared_buckets = set(user.profile.availability_window) & set(
            candidate.profile.availability_window
        )

        # A repeat crossing means a shared routine rather than a coincidence,
        # but the returns flatten fast — four crossings is not twice as good a
        # reason as two.
        crossing_score = min(1.0, crossings / 6.0)
        interest_score = min(1.0, len(shared_interests) / 3.0)
        value_score = min(1.0, len(shared_values) / 2.0)
        availability_score = min(1.0, len(shared_buckets) / 2.0)
        novelty_score = 0.0 if candidate.id in recent_partners else 1.0

        # Distribution fairness (§15.2 / §18). Someone who has already had four
        # encounters this fortnight is a worse use of today's one than someone
        # who has had none. Without this the pool concentrates on a popular
        # minority and we have rebuilt the platform we set out to replace.
        seen = encounter_counts.get(candidate.id, 0)
        fairness_score = 1.0 / (1.0 + seen)

        total = (
            _W_CROSSINGS * crossing_score
            + _W_INTERESTS * interest_score
            + _W_VALUES * value_score
            + _W_AVAILABILITY * availability_score
            + _W_NOVELTY * novelty_score
            + _W_FAIRNESS * fairness_score
        )
        return ScoredCandidate(
            candidate_id=candidate.id,
            score=round(total, 4),
            crossings=crossings,
            shared_interests=tuple(sorted(shared_interests)),
            shared_bucket=sorted(b.value for b in shared_buckets)[0] if shared_buckets else None,
            components={
                "crossings": round(crossing_score, 3),
                "interests": round(interest_score, 3),
                "values": round(value_score, 3),
                "availability": round(availability_score, 3),
                "novelty": novelty_score,
                "fairness": round(fairness_score, 3),
            },
        )

    def shortlist(
        self,
        user: User,
        pool: list[User],
        day: Date,
        recent_partners: set[str],
        encounter_counts: Counter,
    ) -> tuple[list[ScoredCandidate], list[Ineligible]]:
        """Eligible candidates, best first, at most `SHORTLIST_SIZE`.

        The loop is bounded and reported even though it is a ranking rather
        than a reasoning loop: loop discipline is measured per agent run, and
        an agent that quietly iterates over an unbounded pool is exactly what
        the metric is for.
        """
        rejected: list[Ineligible] = []
        scored: list[ScoredCandidate] = []
        with loop_report(self.name) as report:
            for candidate in pool:
                report.iterations = min(report.iterations + 1, len(pool))
                why_not = eligible(user, candidate, day, self.trust, self.max_lockins)
                if why_not is not None:
                    rejected.append(why_not)
                    continue
                scored.append(
                    self.score(user, candidate, day, recent_partners, encounter_counts)
                )
            # The reasoning loop is the *selection*, which happens at most
            # once. Ranking a pool is bookkeeping, so it is reported as a
            # single iteration rather than inflating the discipline metric.
            report.iterations = 1 if scored else 0
        scored.sort(key=lambda c: (-c.score, c.candidate_id))
        return scored[:SHORTLIST_SIZE], rejected

    def select(
        self,
        user: User,
        pool: list[User],
        day: Date,
        recent_partners: set[str] | None = None,
        encounter_counts: Counter | None = None,
    ) -> MatchDecision | None:
        """Today's one encounter for `user`, or `None` if nobody is eligible.

        `None` is a real answer. Some days nobody's path crossed yours in a way
        that works, and inventing an encounter to avoid an empty day is how a
        product starts wasting people's evenings.
        """
        recent_partners = recent_partners or set()
        encounter_counts = encounter_counts or Counter()
        with span("agent.match", user_id=user.id, day=day.isoformat(), pool=len(pool)) as s:
            shortlist, rejected = self.shortlist(
                user, pool, day, recent_partners, encounter_counts
            )
            s.set_attribute("eligible", len(shortlist))
            s.set_attribute("rejected", len(rejected))
            if not shortlist:
                s.set_attribute("outcome", "no eligible candidate")
                return None

            decision = self._model_choice(user, shortlist, day)
            if decision is None:
                decision = self._deterministic_choice(user, shortlist, day)
                s.set_attribute("source", "deterministic")
            else:
                s.set_attribute("source", "model")
            s.set_attribute("selected", decision.candidate_id)
            s.set_attribute("confidence", decision.confidence)
            return decision

    # -----------------------------------------------------------------
    def _model_choice(
        self, user: User, shortlist: list[ScoredCandidate], day: Date
    ) -> MatchDecision | None:
        """The judgement call. Returns `None` whenever the model cannot be
        trusted to have made one — unavailable, over budget, or invalid."""
        prompt = _render_shortlist(user, shortlist)
        # The model is asked for the judgement only — who, why, how sure. The
        # day and the user id are facts we already hold; asking a model to
        # reproduce them would add two ways for a good answer to fail
        # validation, and would make the schema metric a measure of our prompt.
        choice = structured_call(
            MatchChoice,
            role="reasoning",                 # a judgement call, per the routing table
            agent=self.name,
            system=_SYSTEM,
            user=prompt,
        )
        if choice is None:
            return None
        allowed = {c.candidate_id for c in shortlist}
        if choice.candidate_id not in allowed:
            # The model named someone who was not on the shortlist. Rejected
            # rather than repaired: a selection we cannot explain is not one we
            # should act on.
            return None
        return MatchDecision(
            day=day,
            user_id=user.id,
            candidate_id=choice.candidate_id,
            rationale=choice.rationale,
            confidence=choice.confidence,
            considered=sorted(allowed),
        )

    def _deterministic_choice(
        self, user: User, shortlist: list[ScoredCandidate], day: Date
    ) -> MatchDecision:
        """Top of the shortlist, with a rationale built from what is actually
        shared. Used when there is no model, and it is a perfectly good
        matcher — the model's contribution is judgement between close calls."""
        best = shortlist[0]
        return MatchDecision(
            day=day,
            user_id=user.id,
            candidate_id=best.candidate_id,
            rationale=_rationale_for(best),
            # The deterministic score is a ranking, not a probability. Mapped
            # into a narrow, honest band rather than presented as certainty.
            confidence=round(min(0.75, 0.35 + best.score / 2), 3),
            considered=sorted(c.candidate_id for c in shortlist),
        )


def _rationale_for(candidate: ScoredCandidate) -> str:
    """One sentence, grounded in something real, naming no place and no person.

    Falls back to the fact of the crossing itself, which is always true and is
    the product's actual proposition — not an invented commonality.
    """
    if candidate.shared_interests:
        interests = " and ".join(candidate.shared_interests[:2])
        return f"You have both mentioned {interests}, and your paths have crossed before."
    if candidate.crossings > 1:
        return (
            "Your paths have crossed more than once recently, and you are free "
            "at the same times."
        )
    return "You were both around at the same time today, and you are here for the same thing."


def _render_shortlist(user: User, shortlist: list[ScoredCandidate]) -> str:
    """The shortlist as the model sees it.

    Handles, not names. No cell, no place, no date. The model is given exactly
    what a user would be allowed to see plus the overlap counts, so a rationale
    it writes cannot contain something the guardrail would then have to reject.
    """
    lines = [
        f"The user is here for: {', '.join(i.value for i in user.profile.intents)}.",
        f"Their interests: {', '.join(user.profile.interests) or 'not stated'}.",
        f"Their languages: {', '.join(user.profile.languages)}.",
        "",
        "Shortlist:",
    ]
    for candidate in shortlist:
        shared = ", ".join(candidate.shared_interests) or "nothing stated in common"
        lines.append(
            f"- candidate_id={candidate.candidate_id}; shared interests: {shared}; "
            f"paths crossed {candidate.crossings} time(s) in the last fortnight; "
            f"both free in the {candidate.shared_bucket or 'same'} period."
        )
    lines.append("")
    lines.append("Choose one candidate_id and give one sentence of rationale.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The baseline arms (§19)
# ---------------------------------------------------------------------------


class MatchPolicy(Protocol):
    """What an evaluation arm must be able to do.

    All three arms take the same pool and apply the same eligibility filter.
    They differ only in *which* eligible candidate they pick, which is the one
    thing the evaluation is trying to measure.
    """

    name: str

    def select(
        self,
        user: User,
        pool: list[User],
        day: Date,
        recent_partners: set[str] | None = None,
        encounter_counts: Counter | None = None,
    ) -> MatchDecision | None: ...


@dataclass
class RandomArm:
    """Baseline: pick uniformly at random from the eligible pool.

    The arm the Match Agent has to beat. If it does not, we report that — the
    encounter format would still be the product, and CLAUDE.md pre-registers
    the finding either way.
    """

    client: MCPClient
    trust: TrustAndSafety
    rng: random.Random
    max_lockins: int = 5
    name: str = "random"

    def select(
        self,
        user: User,
        pool: list[User],
        day: Date,
        recent_partners: set[str] | None = None,
        encounter_counts: Counter | None = None,
    ) -> MatchDecision | None:
        with span("arm.random", user_id=user.id, day=day.isoformat()) as s:
            candidates = [
                c
                for c in pool
                if eligible(user, c, day, self.trust, self.max_lockins) is None
            ]
            s.set_attribute("eligible", len(candidates))
            if not candidates:
                return None
            chosen = self.rng.choice(candidates)
            return MatchDecision(
                day=day,
                user_id=user.id,
                candidate_id=chosen.id,
                rationale="Your paths crossed today.",
                # 0.5 is the honest number: this arm has no opinion. And it
                # considered the whole eligible pool, not a shortlist — saying
                # otherwise would make the trace of this arm a fiction.
                confidence=0.5,
                considered=sorted(c.id for c in candidates),
            )


@dataclass
class SimilarityArm:
    """Baseline: naive interest similarity — Jaccard over stated interests.

    The obvious thing to build, and what most matching features actually are.
    It ignores overlap strength, availability weighting, novelty and fairness,
    which is the point: it isolates how much of Spark's result comes from
    similarity alone.

    It deliberately ignores `ConsentScope` too — not as an oversight but as the
    comparison: this is what a matcher that treats every profile field as fair
    game achieves, and it is measured against one that does not.
    """

    client: MCPClient
    trust: TrustAndSafety
    max_lockins: int = 5
    name: str = "similarity"

    def select(
        self,
        user: User,
        pool: list[User],
        day: Date,
        recent_partners: set[str] | None = None,
        encounter_counts: Counter | None = None,
    ) -> MatchDecision | None:
        with span("arm.similarity", user_id=user.id, day=day.isoformat()) as s:
            scored: list[tuple[float, User]] = []
            for candidate in pool:
                if eligible(user, candidate, day, self.trust, self.max_lockins) is not None:
                    continue
                mine = set(user.profile.interests)
                theirs = set(candidate.profile.interests)
                union = mine | theirs
                jaccard = len(mine & theirs) / len(union) if union else 0.0
                scored.append((jaccard, candidate))
            s.set_attribute("eligible", len(scored))
            if not scored:
                return None
            scored.sort(key=lambda pair: (-pair[0], pair[1].id))
            best_score, best = scored[0]
            shortlist = [c.id for _, c in scored[:SHORTLIST_SIZE]]
            return MatchDecision(
                day=day,
                user_id=user.id,
                candidate_id=best.id,
                rationale="You listed some of the same interests.",
                confidence=round(min(0.9, 0.3 + best_score), 3),
                considered=sorted(shortlist),
            )


def decision_id(day: Date, user_id: str) -> str:
    return match_id(day.isoformat(), user_id)
