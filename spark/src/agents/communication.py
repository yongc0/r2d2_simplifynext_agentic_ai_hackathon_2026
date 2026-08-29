"""Communication Agent — organisers' class: **Creative/Generative** (Create & Draft).

docs/ARCHITECTURE.md §13.5. Opt-in, and off for most users by default.

Detects a stalling conversation and offers a prompt **grounded in something
both people actually said**. It suggests; it never speaks for the user.

The rule, from CLAUDE.md, stated plainly because it is the one thing this agent
can get badly wrong:

    Do not let the Communication Agent invent a shared interest. A hallucinated
    commonality is a graded fidelity failure and a real user harm.

Two mechanisms enforce it rather than one:

  `ConversationPrompt.grounded_in` requires exactly two entries, one from each
  person, and refuses to validate if either is empty. A prompt that cannot name
  what each person said cannot be constructed.

  `_verify_grounding` then checks that both entries actually appear in the
  stored notes for the respective person. A model that fills the field with
  something plausible does not get past this, and the failure is recorded
  against answer fidelity (metric 6) rather than quietly retried away.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.agents.base import bounded_loop
from src.mcp.registry import MCPClient
from src.models import provider_available, structured_call
from src.safety.guardrails import render
from src.schemas.agents import ConversationDraft, ConversationPrompt
from src.schemas.core import LockIn, User
from src.telemetry.metrics import METRICS
from src.telemetry.trace import span

AGENT_CLASS = "Creative/Generative"

_SYSTEM = """You suggest ONE question two people might ask each other, when \
their conversation has gone quiet.

You are given what each of them has actually said. You must ground the question \
in BOTH: `grounded_in` takes exactly two entries, the first something the first \
person said and the second something the second person said.

You may not invent a shared interest. If the two lists have nothing in common, \
find a question that connects the two DIFFERENT things they each said — that is \
usually a better question anyway.

The prompt contains no name, no place, no distance. One sentence. British \
spelling."""


@dataclass
class CommunicationAgent:
    client: MCPClient
    name: str = "communication"

    def suggest(
        self, lockin: LockIn, user: User, peer: User, now: datetime
    ) -> ConversationPrompt | None:
        """A grounded prompt, or `None`.

        `None` whenever grounding is not possible — no notes on one side, or a
        model that could not stay grounded. Sending nothing is always better
        than sending an invented commonality.
        """
        if not (
            user.consent_scope.allow_conversation_prompts
            and peer.consent_scope.allow_conversation_prompts
        ):
            return None

        with span("agent.communication", lockin_id=lockin.id, user_id=user.id) as s:
            said_by_user = self._what_they_said(lockin, user.id, now)
            said_by_peer = self._what_they_said(lockin, peer.id, now)
            s.set_attribute("grounding.user", len(said_by_user))
            s.set_attribute("grounding.peer", len(said_by_peer))
            if not said_by_user or not said_by_peer:
                # Nothing to ground in. Metric 6 counts this as a non-event
                # rather than a failure: the agent correctly declined.
                s.set_attribute("outcome", "declined — nothing to ground in")
                return None

            prompt: ConversationPrompt | None = None
            # Only retry if there is a provider to retry against; looping
            # against one that is not configured is the circling loop
            # discipline (metric 3) exists to catch.
            if provider_available():
                for _attempt in bounded_loop(self.name):
                    draft = structured_call(
                        ConversationDraft,
                        role="fast",
                        agent=self.name,
                        system=_SYSTEM,
                        user=self._prompt(said_by_user, said_by_peer),
                    )
                    if draft is None:
                        break
                    candidate = ConversationPrompt(
                        lockin_id=lockin.id,
                        prompt=draft.prompt,
                        grounded_in=draft.grounded_in,
                    )
                    if self._verify_grounding(candidate, said_by_user, said_by_peer):
                        prompt = candidate
                        break
                    METRICS.record_fidelity(
                        grounded=False,
                        detail=(
                            f"communication: prompt cited {candidate.grounded_in} but "
                            "neither person said that. Rejected rather than sent — an "
                            "invented commonality is a user harm, not a style issue."
                        ),
                    )
                    # Same prompt, same temperature, same answer. Fall back to
                    # the deterministic prompt, which is grounded by
                    # construction because it can only use the two note lists.
                    break

            if prompt is None:
                prompt = self._deterministic_prompt(lockin, said_by_user, said_by_peer)

            METRICS.record_fidelity(grounded=True)
            safe = render(
                prompt.prompt, user.id, subject_id=peer.id, context="conversation prompt"
            )
            return prompt.model_copy(update={"lockin_id": lockin.id, "prompt": safe})

    # -----------------------------------------------------------------
    def _what_they_said(self, lockin: LockIn, owner_id: str, now: datetime) -> list[str]:
        result = self.client.try_call(
            "spark-profile",
            "read_notes",
            default={"notes": []},
            owner_id=owner_id,
            lockin_id=lockin.id,
            as_of=now.isoformat(),
        ) or {"notes": []}
        return [n["note"] for n in result["notes"]]

    def _prompt(self, said_by_user: list[str], said_by_peer: list[str]) -> str:
        return (
            "The first person has said:\n"
            + "\n".join(f"- {s}" for s in said_by_user[-4:])
            + "\n\nThe second person has said:\n"
            + "\n".join(f"- {s}" for s in said_by_peer[-4:])
            + "\n\nSuggest one question, grounded in both."
        )

    @staticmethod
    def _verify_grounding(
        prompt: ConversationPrompt, said_by_user: list[str], said_by_peer: list[str]
    ) -> bool:
        """Both citations must actually appear in the right person's notes.

        Substring in either direction, so a close paraphrase passes and an
        invention does not.
        """
        first, second = prompt.grounded_in

        def cited(claim: str, source: list[str]) -> bool:
            claim = claim.strip().lower()
            return any(claim in note.lower() or note.lower() in claim for note in source)

        return cited(first, said_by_user) and cited(second, said_by_peer)

    def _deterministic_prompt(
        self, lockin: LockIn, said_by_user: list[str], said_by_peer: list[str]
    ) -> ConversationPrompt:
        """The no-model path. Grounded by construction — it can only use what
        is in the two lists, so it cannot invent anything."""
        mine, theirs = said_by_user[-1], said_by_peer[-1]
        if mine == theirs:
            question = f"You both brought up {mine} — what got you into it?"
        else:
            question = f"You mentioned {mine} and they mentioned {theirs}. Which came first?"
        return ConversationPrompt(
            lockin_id=lockin.id,
            prompt=question,
            grounded_in=[mine, theirs],
        )
