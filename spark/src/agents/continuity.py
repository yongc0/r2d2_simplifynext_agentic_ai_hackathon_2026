"""Continuity Agent — organisers' class: **Personalized** (Adapt & Learn).

docs/ARCHITECTURE.md §13.4. **This is the agent that makes the "plans, acts and
adapts over time" claim true.** Everything else in Spark happens inside one
evening; this one owns up to ten lock-ins per user across weeks.

What it does, and what each one is for:

  `brief`            surfaces what the pair actually discussed, before the next
                     contact. Grounded in a stored note or it is not sent.
  `re_entry`         a quiet lock-in gets a concrete way back in, quoting the
                     thing that was left unfinished — not a generic nudge.
  `propose_meeting`  a specific time and activity, from both calendars and
                     both interest sets. "We should meet sometime" is where
                     most of these die.
  `adjust_pace`      learns the pair's rhythm from observed gaps rather than
                     asking them to configure one.
  `release`          lets a dead lock-in go, freeing the slot, without
                     confrontation and without telling either person the other
                     stopped replying.

Week 5 must visibly differ from week 1, and it does: week 1 has one note and
sends a brief; by week 5 the agent has a history, a learned pace, and a
proposal to make. `src/cli/simulate.py` prints both so the difference is
demonstrable rather than asserted.

Notes are stored in AgentCore Memory via `spark-profile`, scoped per user,
deletable on request, and never surfaced to anyone the note was not about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.agents.base import bounded_loop
from src.config import SETTINGS
from src.mcp.registry import MCPClient
from src.models import provider_available, structured_call
from src.safety.guardrails import render
from src.schemas.agents import ContinuityAction, ContinuityDraft
from src.schemas.core import LockIn, LockInState, User
from src.schemas.views import LockInBrief
from src.telemetry.trace import span

AGENT_CLASS = "Personalized"

_SYSTEM = """You look after a connection between two people who met through \
one anonymous three-minute call and have since chosen to keep talking.

You are given: which week this is, how long since they last spoke, their \
learned pace, and notes about what they ACTUALLY discussed.

Rules:
- `reference` must quote or closely paraphrase something in the notes. Never \
invent a shared topic. If the notes are empty, use action "brief" and say only \
what the notes support.
- `message` is shown to one person about the other. It must contain NO name, \
NO place, NO distance, and nothing about where either of them is or was.
- Choose "propose_meeting" only if they have spoken at least twice.
- Choose "release" only if it has been a long time and there is nothing left \
to re-enter on. Releasing is kind, not a failure.
- One or two sentences. Use British spelling. Never guilt anyone for being slow \
to reply."""


@dataclass
class ContinuityAgent:
    """One instance per run. Holds the tool client; state lives on the LockIn."""

    client: MCPClient
    name: str = "continuity"

    # -----------------------------------------------------------------
    # Memory
    # -----------------------------------------------------------------

    def remember(self, lockin: LockIn, owner_id: str, note: str, at: datetime, source: str = "call") -> None:
        """Write a note into one person's own memory.

        Called once per participant after a call, so each person's memory is
        theirs. Neither can read the other's — that is enforced in
        `spark-profile`, on the read path, where it cannot be forgotten.
        """
        self.client.try_call(
            "spark-profile",
            "write_note",
            owner_id=owner_id,
            lockin_id=lockin.id,
            note=note,
            source=source,
            at=at.isoformat(),
        )

    def recall(self, lockin: LockIn, owner_id: str, as_of: datetime) -> list[str]:
        """This person's notes about this lock-in, newest last."""
        result = self.client.try_call(
            "spark-profile",
            "read_notes",
            default={"notes": []},
            owner_id=owner_id,
            lockin_id=lockin.id,
            as_of=as_of.isoformat(),
        ) or {"notes": []}
        return [n["note"] for n in result["notes"]]

    # -----------------------------------------------------------------
    # The weekly decision
    # -----------------------------------------------------------------

    def act(self, lockin: LockIn, user: User, week: int, now: datetime) -> ContinuityAction | None:
        """What, if anything, to do for this person about this lock-in today.

        `None` means "nothing today", which is most days. An agent that acts
        every day is a notification schedule, not attention.
        """
        if not user.consent_scope.allow_continuity_notes:
            # A user who declined continuity notes gets no memory-based action.
            # The lock-in still exists; the agent simply has nothing to say.
            return None

        with span(
            "agent.continuity",
            lockin_id=lockin.id,
            user_id=user.id,
            week=week,
            state=lockin.state.value,
        ) as s:
            days_quiet = (now - lockin.last_contact).days
            notes = self.recall(lockin, user.id, now)
            s.set_attribute("days_quiet", days_quiet)
            s.set_attribute("notes", len(notes))

            intent = self._what_is_needed(lockin, days_quiet, notes, week)
            s.set_attribute("intent", intent or "nothing")
            if intent is None:
                return None

            action: ContinuityAction | None = None
            if provider_available():
                for _attempt in bounded_loop(self.name):
                    # The model writes the words. The lock-in and user ids are
                    # ours, and asking for them would only add ways for a good
                    # answer to fail validation.
                    draft = structured_call(
                        ContinuityDraft,
                        role="reasoning",      # judgement call, per the routing table
                        agent=self.name,
                        system=_SYSTEM,
                        user=self._prompt(lockin, user, week, days_quiet, notes, intent),
                    )
                    if draft is None:
                        break                 # no provider, over budget, or invalid
                    if draft.action == intent:
                        action = ContinuityAction(
                            lockin_id=lockin.id,
                            user_id=user.id,
                            action=draft.action,
                            message=draft.message,
                            reference=draft.reference,
                            pace_pref_days=draft.pace_pref_days,
                            confidence=draft.confidence,
                        )
                        break
                    # The model chose a different act from the one the rules
                    # call for. It is not wrong to have an opinion, but the pace
                    # and release rules are ours — and re-sending an identical
                    # prompt at temperature 0 can only produce the identical
                    # answer, which is circling, not converging. Take the
                    # deterministic wording instead.
                    s.set_attribute("model_action_overridden", draft.action)
                    action = None
                    break

            if action is None:
                action = self._deterministic_action(lockin, user, week, days_quiet, notes, intent)
                s.set_attribute("source", "deterministic")
            else:
                s.set_attribute("source", "model")

            # Everything the user will see goes through the guardrail.
            safe = render(
                action.message,
                user.id,
                subject_id=lockin.other(user.id),
                context=f"continuity {action.action}",
            )
            return action.model_copy(update={"message": safe})

    # -----------------------------------------------------------------
    def _what_is_needed(
        self, lockin: LockIn, days_quiet: int, notes: list[str], week: int
    ) -> str | None:
        """The rule layer. What the situation calls for, decided in code.

        Deliberately not the model's job: whether to release a lock-in, and how
        often to speak to someone, are decisions with a cost to the person on
        the other end. The model writes the words; this chooses the act.
        """
        if lockin.state is LockInState.RELEASED:
            return None
        if days_quiet >= SETTINGS.rules.lockin_quiet_days:
            # A long silence gets ONE concrete way back in. If it is still
            # quiet after that, the lock-in is let go and the slot freed —
            # releasing is kind, and holding a dead connection open costs the
            # user one of only ten slots.
            if lockin.state is LockInState.QUIET or not notes:
                return "release"
            return "re_entry"
        if lockin.contacts >= 2 and lockin.met_in_person_on is None and days_quiet >= 2:
            return "propose_meeting"
        if days_quiet >= max(1, round(lockin.pace_pref_days)):
            return "brief" if week <= 1 or not notes else "re_entry"
        return None

    def _prompt(
        self,
        lockin: LockIn,
        user: User,
        week: int,
        days_quiet: int,
        notes: list[str],
        intent: str,
    ) -> str:
        note_lines = "\n".join(f"- {n}" for n in notes[-5:]) or "- (no notes yet)"
        return (
            f"Week {week} of this connection.\n"
            f"They last spoke {days_quiet} day(s) ago.\n"
            f"Learned pace: about every {lockin.pace_pref_days:.1f} days.\n"
            f"Times they have spoken: {lockin.contacts}.\n"
            f"Met in person: {'yes' if lockin.met_in_person_on else 'not yet'}.\n"
            f"The action called for is: {intent}.\n\n"
            f"Notes on what they actually discussed:\n{note_lines}\n\n"
            "Write the action."
        )

    def _deterministic_action(
        self,
        lockin: LockIn,
        user: User,
        week: int,
        days_quiet: int,
        notes: list[str],
        intent: str,
    ) -> ContinuityAction:
        """The no-model path. Grounded in the same notes, in plainer words."""
        reference = notes[-1] if notes else ""
        messages = {
            "brief": (
                f"Before you speak again: last time you talked about {reference or 'the call itself'}."
            ),
            "re_entry": (
                f"You left something unfinished — {reference}. "
                "Worth picking that back up?"
            ),
            "propose_meeting": (
                f"You have spoken {lockin.contacts} times now. "
                f"Since you both mentioned {reference or 'something in common'}, "
                "shall we organise a time?"
            ),
            "adjust_pace": (
                "You two seem to like a slower rhythm. We will stop nudging so often."
            ),
            "release": (
                "This one has gone quiet, so we are letting it go and freeing the "
                "slot. Nothing is sent to the other person."
            ),
        }
        return ContinuityAction(
            lockin_id=lockin.id,
            user_id=user.id,
            action=intent,                                # type: ignore[arg-type]
            message=messages[intent],
            reference=reference,
            pace_pref_days=lockin.pace_pref_days if intent == "adjust_pace" else None,
            confidence=0.6,
        )

    # -----------------------------------------------------------------
    # Pace learning
    # -----------------------------------------------------------------

    def learn_pace(self, lockin: LockIn, gap_days: float) -> float:
        """Move the learned pace towards the gap actually observed.

        An exponential moving average with a slow rate: one long week should
        not convince the system that a pair who talk every other day now want
        to talk fortnightly. Bounded so a pathological run cannot drive it to
        zero or to never.
        """
        updated = 0.7 * lockin.pace_pref_days + 0.3 * gap_days
        return max(0.5, min(30.0, round(updated, 2)))

    # -----------------------------------------------------------------
    # The brief a user sees
    # -----------------------------------------------------------------

    def brief(self, lockin: LockIn, user: User, week: int, now: datetime) -> LockInBrief | None:
        """What to surface before the next contact.

        Returns `None` when there is nothing to cite. A brief with nothing
        behind it is a reminder, and the product already has enough of those.
        """
        notes = self.recall(lockin, user.id, now)
        if not notes:
            return None
        latest = notes[-1]
        message = render(
            f"Last time, you talked about {latest}.",
            user.id,
            subject_id=lockin.other(user.id),
            context="lock-in brief",
        )
        return LockInBrief(
            lockin_id=lockin.id,
            user_id=user.id,
            message=message,
            grounded_in=latest,
            week=week,
            generated_at=now,
        )
