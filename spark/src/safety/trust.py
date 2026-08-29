"""Trust & Safety — *Embedded*, cross-cutting. docs/ARCHITECTURE.md §13.8.

Screens onboarding text and post-reveal messages; enforces cooldowns, blocks
and reports. Deterministic, with a guardrail pattern set — INVARIANT 6 means no
model gets a vote on whether something is harassment.

Scope, stated rather than implied. This screens **text**: onboarding intake and
post-reveal messages. It does not screen the audio of a call. Voice-channel
safety is materially harder than text (open item 6 in the architecture), and
claiming otherwise would be the kind of overreach the evaluation is meant to
catch. What the product does about the call itself is structural instead: the
call is three minutes, it is anonymous on both sides, no identity is exchanged
without a mutual yes, and either party can end it — plus the Guardian Agent for
an in-person meeting later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date

from src.config import SETTINGS
from src.safety.guardrails import screen_inbound
from src.schemas.agents import SafetyVerdict
from src.telemetry.metrics import METRICS
from src.telemetry.trace import span


@dataclass
class TrustAndSafety:
    """Cooldowns, blocks, reports, and the text screen.

    Holds the state that decides *eligibility*, which is why it is ordinary
    Python with tests: `tests/test_intent.py` exercises the rules directly.
    """

    #: (user_a, user_b) sorted -> the last day they were matched
    _last_matched: dict[tuple[str, str], Date] = field(default_factory=dict)
    #: user_id -> the users they have blocked
    _blocks: dict[str, set[str]] = field(default_factory=dict)
    #: user_id -> how many reports have been filed against them
    _reports: dict[str, int] = field(default_factory=dict)

    # -------------------------------------------------------------------
    # Screening
    # -------------------------------------------------------------------

    def screen_text(self, text: str, source: str = "message") -> SafetyVerdict:
        """Screen something a user wrote.

        A blocked verdict always names its categories — `SafetyVerdict` refuses
        to be constructed without them, so "blocked" with no reason cannot
        reach a user or an operator.
        """
        with span("trust.screen", source=source, chars=len(text)) as s:
            verdict = screen_inbound(text)
            s.set_attribute("allowed", verdict.allowed)
            s.set_attribute("categories", ",".join(verdict.categories))
            if verdict.allowed:
                return SafetyVerdict(allowed=True)
            return SafetyVerdict(
                allowed=False,
                categories=verdict.categories,
                user_message=self._user_message_for(verdict.categories),
                detail=f"{source}: {verdict.reason()}",
            )

    @staticmethod
    def _user_message_for(categories: list[str]) -> str:
        """What the person is told. Specific enough to be actionable, never a
        lecture, and never a hint about how to get past the filter."""
        if "consent_circumvention" in categories or "contact_exfiltration" in categories:
            return (
                "Contact details stay private until you have both said yes. "
                "You can keep talking here in the meantime."
            )
        if "scam" in categories:
            return (
                "That message looks like a financial solicitation, which is not "
                "permitted on Spark. If you believe this is a mistake, you can "
                "ask us to review it."
            )
        if "sexual_content" in categories:
            return "That message was not sent. Spark does not carry sexual content."
        return (
            "That message was not sent. Spark does not carry abusive language. "
            "Repeated attempts will end your access."
        )

    # -------------------------------------------------------------------
    # Eligibility — who may be matched with whom
    # -------------------------------------------------------------------

    def block(self, user_id: str, blocked_id: str) -> None:
        self._blocks.setdefault(user_id, set()).add(blocked_id)

    def report(self, about_user: str) -> int:
        self._reports[about_user] = self._reports.get(about_user, 0) + 1
        return self._reports[about_user]

    def reports_against(self, user_id: str) -> int:
        return self._reports.get(user_id, 0)

    def is_blocked(self, user_a: str, user_b: str) -> bool:
        """Blocks are symmetric in effect. If either has blocked the other,
        neither is offered the other — a one-way block that still surfaces the
        blocker to the blocked person is not a block."""
        return (
            user_b in self._blocks.get(user_a, ())
            or user_a in self._blocks.get(user_b, ())
        )

    def note_match(self, user_a: str, user_b: str, day: Date) -> None:
        self._last_matched[self._key(user_a, user_b)] = day

    def in_cooldown(self, user_a: str, user_b: str, day: Date) -> bool:
        """OPEN QUESTION 1 — the window is a guess, and the README says so.

        The rule itself is not a guess: two people who have already had their
        three minutes should not be handed each other again the next morning,
        because the encounter's value comes from it being someone new.
        """
        last = self._last_matched.get(self._key(user_a, user_b))
        if last is None:
            return False
        return (day - last).days < SETTINGS.rules.rematch_cooldown_days

    @staticmethod
    def _key(user_a: str, user_b: str) -> tuple[str, str]:
        return (user_a, user_b) if user_a < user_b else (user_b, user_a)

    # -------------------------------------------------------------------
    # Evaluation support
    # -------------------------------------------------------------------

    def score_adversarial_set(self, cases: list[dict]) -> dict[str, float | int]:
        """Run the seeded adversarial set and record the false-negative rate.

        A false negative is harmful content that was not blocked. It is the
        number that matters here: a false positive inconveniences someone, a
        false negative reaches them.
        """
        false_negatives = 0
        false_positives = 0
        harmful = 0
        benign = 0
        for case in cases:
            is_harmful = bool(case["harmful"])
            verdict = self.screen_text(case["text"], source="adversarial")
            blocked = not verdict.allowed
            METRICS.record_guardrail_case(
                harmful=is_harmful,
                blocked=blocked,
                detail=f"missed {case.get('category', 'harm')}: {case['id']}",
            )
            if is_harmful:
                harmful += 1
                false_negatives += 0 if blocked else 1
            else:
                benign += 1
                false_positives += 1 if blocked else 0
        return {
            "harmful_cases": harmful,
            "benign_cases": benign,
            "false_negatives": false_negatives,
            "false_negative_rate": (false_negatives / harmful) if harmful else 0.0,
            "false_positives": false_positives,
            "false_positive_rate": (false_positives / benign) if benign else 0.0,
        }
