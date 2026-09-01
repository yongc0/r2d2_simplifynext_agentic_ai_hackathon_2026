"""Encounter Delivery — organisers' class: **Transaction** (Do & Automate).

Owns the whole encounter: notification -> dual accept -> voice bridge ->
hard three-minute stop -> private post-call prompt -> reveal or silent close.
docs/ARCHITECTURE.md §13.3.

`DETERMINISTIC`. There is no model call in this file and there must never be
one. Everything it does is either a consent decision or a consequence of one,
and INVARIANT 6 says a model is never the last thing between a stranger and
someone's identity.

The five invariants it enforces, and where:

  1  no identity before a mutual yes      -> `reveal_or_close`, via
                                             `safety.consent.build_reveal`
  2  a decline emits no signal            -> `close_out_for`, which is handed
                                             an id and a time and nothing else
  3  no place, distance or coordinate     -> every string leaves through
                                             `safety.guardrails.render`
  4  the call stops at 180 seconds        -> `spark-voice`, where duration is
                                             not a parameter
  5  consent events are append-only       -> `safety.consent.ConsentLedger`
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.config import SETTINGS
from src.mcp.registry import MCPClient
from src.mcp.services import WORLD
from src.safety.consent import (
    ConsentLedger,
    accept_window_closes,
    build_close_out,
    build_reveal,
    consent_window_closes,
    is_mutual_yes,
    reveal_permitted,
)
from src.safety.guardrails import IDENTITIES, render
from src.schemas.core import (
    Consent,
    ConsentDecision,
    ConsentStage,
    Encounter,
    EncounterState,
    TimeBucket,
    User,
)
from src.schemas.views import (
    AnonymousPeer,
    CloseOutView,
    ConsentPrompt,
    EncounterCard,
    RevealView,
)
from src.telemetry.trace import span

AGENT_CLASS = "Transaction"


class CallsDisabled(Exception):
    """A participant has turned off calls from Spark.

    Deliberately NOT a `DeliveryRefused`, which means "the caller has a bug and
    should be fixed". This is a person exercising a setting, and the graph must
    end the encounter quietly rather than raise: from the other side it has to
    be indistinguishable from a no-show (INVARIANT 2).
    """


class DeliveryRefused(Exception):
    """The encounter cannot proceed, and the reason is a programming error
    rather than a user's choice."""


@dataclass
class EncounterDelivery:
    """One instance per run; holds the ledger and the tool client."""

    client: MCPClient
    ledger: ConsentLedger

    # -----------------------------------------------------------------
    # Notification
    # -----------------------------------------------------------------

    def build_card(
        self,
        encounter: Encounter,
        viewer: User,
        peer: User,
        rationale: str,
        shared_interests: list[str],
        shared_bucket: TimeBucket | None,
        notified_at: datetime,
    ) -> EncounterCard:
        """What the user is shown when today's encounter is offered.

        `AnonymousPeer` has nowhere to put a name or a place, and `rationale`
        goes through `render` — so the card cannot carry an identity even if the
        Match Agent tried to write one into its sentence.
        """
        with span("delivery.card", encounter_id=encounter.id, viewer=viewer.id):
            safe_rationale = render(
                rationale,
                viewer.id,
                subject_id=peer.id,
                context="encounter card rationale",
            )
            return EncounterCard(
                encounter_id=encounter.id,
                peer=AnonymousPeer(
                    handle=peer.handle,
                    intents=list(peer.profile.intents),
                    languages=list(peer.profile.languages),
                    shared_interests=shared_interests[:5],
                    shared_bucket=shared_bucket,
                ),
                rationale=safe_rationale,
                call_seconds=SETTINGS.rules.call_seconds,
                respond_by=accept_window_closes(notified_at),
            )

    # -----------------------------------------------------------------
    # Gate 1 — will you take the call
    # -----------------------------------------------------------------

    def record_accept(
        self,
        encounter: Encounter,
        user_id: str,
        decision: ConsentDecision,
        at: datetime,
    ) -> Consent:
        """Append one accept-stage decision.

        `encounter.accepted` is maintained for the graph's own use and is never
        rendered: a count of who has accepted is exactly the observable signal
        INVARIANT 2 forbids.
        """
        entry = self.ledger.record(encounter.id, user_id, ConsentStage.ACCEPT, decision, at)
        if decision is ConsentDecision.YES and user_id not in encounter.accepted:
            encounter.accepted.append(user_id)
        return entry

    def both_accepted(self, encounter: Encounter) -> bool:
        return is_mutual_yes(self.ledger, encounter, ConsentStage.ACCEPT)

    # -----------------------------------------------------------------
    # The call
    # -----------------------------------------------------------------

    def connect(self, encounter: Encounter, started_at: datetime) -> tuple[datetime, int]:
        """Open the bridge. Returns when the call ended and how long it ran.

        The duration comes back from `spark-voice` and is not negotiable —
        INVARIANT 4. If the bridge fails, this raises `ToolError` and the graph
        abandons the encounter; neither party is told the failure was ours,
        because "the other person didn't join" and "our bridge fell over" must
        not be distinguishable from the outside either.
        """
        with span("delivery.connect", encounter_id=encounter.id) as s:
            if not self.both_accepted(encounter):
                raise DeliveryRefused(
                    f"refusing to connect encounter {encounter.id}: both parties "
                    "must have accepted first. This is a caller bug — the graph "
                    "should have routed to ABANDONED."
                )
            # Both people, not just the viewer: a call has two ends, and one
            # person opting out is enough to stop it. Checked before the tool
            # call as well as inside it — the bridge is the lock, this is the
            # door not being opened in the first place.
            blocked = [
                uid
                for uid in encounter.participants()
                if uid in WORLD.users
                and not WORLD.users[uid].consent_scope.allow_calls
            ]
            if blocked:
                s.set_attribute("calls_disabled", len(blocked))
                raise CallsDisabled(
                    f"refusing to connect encounter {encounter.id}: calls from "
                    "Spark are turned off for a participant. The encounter ends "
                    "quietly, and the other party is told nothing that would "
                    "distinguish this from a no-show (INVARIANT 2)."
                )

            result = self.client.call(
                "spark-voice",
                "connect_call",
                encounter_id=encounter.id,
                both_accepted=True,
                calls_allowed=True,
                started_at=started_at.isoformat(),
            )
            duration = int(result["duration_s"])
            if duration > SETTINGS.rules.call_seconds:
                # Defence in depth. The bridge owns the cap; this is the second
                # lock on the same door, because a call that overruns is a
                # promise broken to both people on it.
                raise DeliveryRefused(
                    f"spark-voice returned a {duration}s call for encounter "
                    f"{encounter.id}, over the {SETTINGS.rules.call_seconds}s "
                    "limit. The call is void. INVARIANT 4 is not negotiable."
                )
            ended = started_at.replace(microsecond=0) + _seconds(duration)
            s.set_attribute("duration_s", duration)
            return ended, duration

    # -----------------------------------------------------------------
    # Gate 2 — may we swap names
    # -----------------------------------------------------------------

    def consent_prompt(self, encounter: Encounter, call_ended: datetime) -> ConsentPrompt:
        """The post-call question, asked privately and identically of both.

        Fixed wording, from `ConsentPrompt`. It never says whether the other
        person has answered — a "they're deciding" line would be a signal, and
        a "they already said yes" line would be coercion.
        """
        return ConsentPrompt(
            encounter_id=encounter.id,
            respond_by=consent_window_closes(call_ended),
        )

    def record_reveal_decision(
        self,
        encounter: Encounter,
        user_id: str,
        decision: ConsentDecision,
        at: datetime,
    ) -> Consent:
        return self.ledger.record(encounter.id, user_id, ConsentStage.REVEAL, decision, at)

    # -----------------------------------------------------------------
    # The outcome
    # -----------------------------------------------------------------

    def reveal_or_close(
        self,
        encounter: Encounter,
        users: dict[str, User],
        lockin_id: str,
        at: datetime,
    ) -> dict[str, RevealView | CloseOutView]:
        """The one place an encounter's outcome is decided.

        Returns a view per participant. Either both get a `RevealView`, or both
        get the identical `CloseOutView` — there is no third case and no
        asymmetric case, which is what makes INVARIANT 2 hold at the level of
        the whole flow rather than one function.
        """
        if encounter.call_ended is None:
            raise DeliveryRefused(
                f"encounter {encounter.id} has no call_ended; a reveal decision "
                "cannot be taken before the call has happened."
            )
        with span("delivery.outcome", encounter_id=encounter.id) as s:
            mutual = reveal_permitted(self.ledger, encounter)
            s.set_attribute("mutual", mutual)
            if not mutual:
                # Note what is NOT read here: nobody's decision. The close-out
                # is built from an id and the call-end time, so it is identical
                # for a decline, a timeout, and a both-declined.
                return {
                    user_id: self.close_out_for(encounter, user_id)
                    for user_id in encounter.participants()
                }

            IDENTITIES.mark_revealed(*encounter.participants())
            views: dict[str, RevealView | CloseOutView] = {}
            for viewer_id in encounter.participants():
                other_id = encounter.other(viewer_id)
                views[viewer_id] = build_reveal(
                    self.ledger,
                    encounter,
                    viewer_id=viewer_id,
                    other=users[other_id],
                    lockin_id=lockin_id,
                    at=at,
                )
            return views

    def close_out_for(self, encounter: Encounter, viewer_id: str) -> CloseOutView:
        """INVARIANT 2. A thin wrapper that keeps the narrow signature narrow.

        It would be so easy, and so wrong, to pass the ledger in here to write
        a warmer message. Every such message is a channel.
        """
        assert encounter.call_ended is not None      # checked by the caller
        return build_close_out(encounter.id, viewer_id, encounter.call_ended)

    # -----------------------------------------------------------------
    # State transitions the graph delegates here
    # -----------------------------------------------------------------

    def abandon(self, encounter: Encounter, reason: str) -> None:
        """A normal terminal state, not an error (§14).

        The reason is recorded for the operator and never rendered — the users
        see nothing at all, which is the whole point.
        """
        with span("delivery.abandon", encounter_id=encounter.id, reason=reason):
            encounter.transition_to(EncounterState.ABANDONED)


def _seconds(count: int):
    from datetime import timedelta

    return timedelta(seconds=count)
