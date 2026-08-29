"""The consent gate. Ordinary Python, fully tested, no model anywhere near it.

This module is the product. Read it before changing anything in it.

Four of the six invariants in CLAUDE.md are enforced here, and each is enforced
*structurally* rather than by remembering to be careful:

INVARIANT 1 — no identity before a mutual yes.
    `RevealView` is the only object carrying an identity, and `build_reveal` is
    the only function that constructs one. It demands a mutual `yes` at the
    reveal stage and raises `RevealRefused` otherwise. There is no flag, no
    override argument, and no code path around it.

INVARIANT 2 — a decline emits no observable signal.
    `build_close_out` is never given the other party's decision. It takes an
    encounter id, a viewer and the call-end time, and nothing else. It cannot
    vary with an answer it was not handed. The timestamp it renders is a fixed
    offset from the end of the call, so the *timing* carries no signal either.
    This is the invariant most easily broken by a well-meaning feature ("show
    them it's still pending!"), which is why it is enforced by a signature.

INVARIANT 5 — consent events are append-only.
    `ConsentLedger.record` appends and never mutates. `records_for` returns
    copies. Nothing in the package joins the ledger into a view: the only
    ledger-derived value that reaches a user is the single boolean that opens
    the reveal, and it is only ever read for a pair that both said yes.

INVARIANT 6 — no model decides any of this.
    There is no import of a model, an agent, or a prompt in this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.config import SETTINGS
from src.schemas.core import (
    Consent,
    ConsentDecision,
    ConsentStage,
    Encounter,
    User,
)
from src.schemas.views import CloseOutView, RevealView


class RevealRefused(Exception):
    """Raised when a reveal is attempted without a mutual yes.

    Deliberately an exception rather than a `None` return: a caller that
    forgets to check a return value gets a crash and a stack trace, not a
    silent disclosure.
    """


class ConsentViolation(Exception):
    """Raised when something tries to mutate or re-answer the ledger."""


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


@dataclass
class ConsentLedger:
    """Append-only record of every consent decision (INVARIANT 5).

    In production this is an immutable event store. Here it is a list that
    refuses to be edited, which is the same guarantee at simulation scale.
    """

    _records: list[Consent] = field(default_factory=list)

    def record(
        self,
        encounter_id: str,
        user_id: str,
        stage: ConsentStage,
        decision: ConsentDecision,
        timestamp: datetime,
    ) -> Consent:
        """Append one decision. A second answer for the same (encounter, user,
        stage) is refused rather than overwriting the first — an editable
        consent record is not a consent record."""
        existing = self.find(encounter_id, user_id, stage)
        if existing is not None:
            raise ConsentViolation(
                f"user {user_id} has already answered the {stage.value} stage of "
                f"encounter {encounter_id} with {existing.decision.value!r}. "
                "Consent records are append-only and are never revised; if the "
                "product needs a change-of-mind flow, it needs its own stage."
            )
        entry = Consent(
            encounter_id=encounter_id,
            user_id=user_id,
            stage=stage,
            decision=decision,
            timestamp=timestamp,
        )
        self._records.append(entry)
        return entry

    def find(
        self, encounter_id: str, user_id: str, stage: ConsentStage
    ) -> Consent | None:
        for entry in self._records:
            if (
                entry.encounter_id == encounter_id
                and entry.user_id == user_id
                and entry.stage == stage
            ):
                return entry
        return None

    def records_for(self, encounter_id: str) -> list[Consent]:
        """Copies, so a caller cannot reach in and edit history."""
        return [r.model_copy(deep=True) for r in self._records if r.encounter_id == encounter_id]

    def all_records(self) -> list[Consent]:
        return [r.model_copy(deep=True) for r in self._records]

    def __len__(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def decision_for(
    ledger: ConsentLedger, encounter_id: str, user_id: str, stage: ConsentStage
) -> ConsentDecision:
    """One user's answer, with no answer meaning `TIMEOUT`.

    Absence and refusal are collapsed on purpose. Everywhere downstream, "did
    not answer" and "said no" must behave identically, and the cheapest way to
    guarantee that is to stop distinguishing them this early.
    """
    entry = ledger.find(encounter_id, user_id, stage)
    return entry.decision if entry is not None else ConsentDecision.TIMEOUT


def is_mutual_yes(
    ledger: ConsentLedger, encounter: Encounter, stage: ConsentStage
) -> bool:
    """True only when BOTH participants said yes at this stage.

    The single ledger-derived boolean allowed to influence anything a user
    sees, and only in the direction that opens a reveal both people asked for.
    """
    return all(
        decision_for(ledger, encounter.id, user_id, stage) is ConsentDecision.YES
        for user_id in encounter.participants()
    )


def reveal_permitted(ledger: ConsentLedger, encounter: Encounter) -> bool:
    """INVARIANT 1, as one function.

    Three conditions, all required:
      - the call actually happened (you cannot reveal from a notification), and
      - the encounter is at the post-call consent gate or past it, and
      - both parties said yes at the reveal stage.
    """
    if encounter.call_ended is None:
        return False
    return is_mutual_yes(ledger, encounter, ConsentStage.REVEAL)


def build_reveal(
    ledger: ConsentLedger,
    encounter: Encounter,
    viewer_id: str,
    other: User,
    lockin_id: str,
    at: datetime,
) -> RevealView:
    """The ONLY constructor of an identity-bearing view (INVARIANT 1).

    `other` is a full `User` — identity included — because after a mutual yes
    that is exactly what may be shared. Before one, this function raises, and
    nothing else in the codebase builds a `RevealView`.
    """
    if viewer_id not in encounter.participants():
        raise RevealRefused(
            f"user {viewer_id} is not a participant in encounter {encounter.id}"
        )
    if other.id != encounter.other(viewer_id):
        raise RevealRefused(
            f"refusing to reveal {other.id} to {viewer_id}: they are not the "
            f"counterpart in encounter {encounter.id}"
        )
    if not reveal_permitted(ledger, encounter):
        raise RevealRefused(
            f"encounter {encounter.id} has no mutual yes at the reveal stage. "
            "An identity is never disclosed on one person's consent, on a "
            "timeout, or on an operator's judgement."
        )
    return RevealView(
        encounter_id=encounter.id,
        lockin_id=lockin_id,
        display_name=other.identity.display_name,
        contact_handle=f"spark:{other.handle}",
        revealed_at=at,
    )


def build_close_out(encounter_id: str, viewer_id: str, call_ended: datetime) -> CloseOutView:
    """INVARIANT 2, enforced by this signature.

    Look at what this function is NOT given: the other party's decision, the
    ledger, the encounter, or anything that could carry one. It is given an id,
    a viewer and the moment the call ended. The output therefore cannot depend
    on how — or whether — the other person answered, no matter what a future
    change to the body does.

    `viewer_id` is accepted so callers read naturally and so a per-user audit
    log can be written; it deliberately does not appear in the output, because
    a view that differs between the two participants is a channel between them.

    The timestamp is a fixed offset from the end of the call. If it were "when
    the second answer arrived", a fast close-out would mean an early decline
    and a slow one would mean a long deliberation, and the clock would be
    saying what the words refuse to.
    """
    if not viewer_id:
        raise ValueError("build_close_out needs a viewer id for the audit log")
    return CloseOutView(
        encounter_id=encounter_id,
        available_at=call_ended
        + timedelta(minutes=SETTINGS.rules.close_out_delay_minutes),
    )


def accept_window_closes(notified_at: datetime) -> datetime:
    return notified_at + timedelta(minutes=SETTINGS.rules.accept_window_minutes)


def consent_window_closes(call_ended: datetime) -> datetime:
    return call_ended + timedelta(minutes=SETTINGS.rules.consent_window_minutes)
