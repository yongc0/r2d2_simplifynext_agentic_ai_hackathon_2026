"""Guardian Agent — organisers' class: **Embedded** (Live Where People Work).

docs/ARCHITECTURE.md §13.7. A discreet in-app action triggers a preconfigured
interruption that gives the user a natural reason to leave, followed by a
private check-in.

`DETERMINISTIC`. No model call. Somebody triggering this is having a bad
evening, and the response must be the same one they configured, every time,
with no latency and no chance of a creative rewrite.

The line this agent does not cross, from CLAUDE.md:

    Do not make Guardian Mode imitate a system or OS-level alert. It is a
    safety feature, not a deception tool.

`GuardianPlan.channel` is restricted to `in_app_call` and `in_app_message`.
There is no "fake system notification" option to pick, and adding one would
mean widening a Literal that this docstring explains — which is the point of
putting the constraint in the schema rather than in a code review.

Why it matters that the excuse is *preconfigured*: the person chooses their own
words when they are calm, not while they are trying to leave. That is also why
the check-in is timed rather than triggered — if they do not answer it, that
itself is the signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.schemas.agents import GuardianPlan
from src.telemetry.trace import span

AGENT_CLASS = "Embedded"

#: The default excuses. Ordinary, unremarkable, and true-sounding without
#: pretending to be from anyone but the app the person is already holding.
_DEFAULT_EXCUSES = (
    "Your reminder: you said you needed to leave by now.",
    "Your reminder: call back about tomorrow morning.",
)


@dataclass
class IncidentLog:
    """Append-only record of Guardian activations.

    Separate from the consent ledger and never joined to it. An incident is an
    operational safety record; a consent event is a person's decision. Mixing
    them would make one of the two harder to reason about.
    """

    _entries: list[dict] = field(default_factory=list)

    def record(self, user_id: str, kind: str, at: datetime, detail: str = "") -> None:
        self._entries.append(
            {"user_id": user_id, "kind": kind, "at": at.isoformat(), "detail": detail}
        )

    def for_user(self, user_id: str) -> list[dict]:
        return [e for e in self._entries if e["user_id"] == user_id]

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class GuardianAgent:
    """Personal safety, embedded in the app the person is already in."""

    log: IncidentLog = field(default_factory=IncidentLog)
    name: str = "guardian"

    def plan(
        self,
        user_id: str,
        at: datetime,
        excuse: str | None = None,
        channel: str = "in_app_call",
        trusted_contact: bool = False,
    ) -> GuardianPlan:
        """Build the interruption. Preconfigured, not generated.

        `excuse` is the user's own wording if they set one. It is not passed to
        a model, and it is not improved.
        """
        if channel not in ("in_app_call", "in_app_message"):
            raise ValueError(
                f"Guardian channel {channel!r} is not permitted. Guardian Mode "
                "never imitates a system or OS-level alert; the only channels "
                "are in_app_call and in_app_message (§13.7)."
            )
        with span("agent.guardian", user_id=user_id, channel=channel):
            self.log.record(user_id, "activation", at)
            return GuardianPlan(
                user_id=user_id,
                channel=channel,                        # type: ignore[arg-type]
                excuse_text=excuse or _DEFAULT_EXCUSES[0],
                check_in_after_minutes=20,
                trusted_contact_notified=trusted_contact,
            )

    def check_in_due_at(self, plan: GuardianPlan, activated_at: datetime) -> datetime:
        return activated_at + timedelta(minutes=plan.check_in_after_minutes)

    def record_check_in(self, user_id: str, at: datetime, answered: bool) -> None:
        """An unanswered check-in is itself the signal.

        Recorded either way. What an operator does with an unanswered one is a
        policy question this MVP does not answer, and it is listed as such in
        the README rather than pretended away.
        """
        self.log.record(
            user_id,
            "check_in",
            at,
            detail="answered" if answered else "NO ANSWER — escalate per policy",
        )

    def plan_first_meeting(self, user_id: str, meeting_at: datetime) -> dict:
        """The timed check-in after any first in-person meeting.

        Offered automatically rather than opt-in: the first meeting is the
        moment the product's risk profile changes, and asking someone to
        remember to switch on a safety feature is asking at the wrong time.
        """
        self.log.record(user_id, "first_meeting_scheduled", meeting_at)
        return {
            "user_id": user_id,
            "check_in_at": (meeting_at + timedelta(hours=2)).isoformat(),
            "message": (
                "We will check in two hours after you meet. If you would rather "
                "we did not, you can switch this off."
            ),
        }
