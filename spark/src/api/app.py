"""The FastAPI app.

Every route is a thin wrapper over `SparkSession`, which is a thin wrapper over
the supervisor graph. Nothing here decides an outcome, screens a string, or
builds an identity — those live in `src/graph/` and `src/safety/`, where they
are tested.

Mounted under `/api` so a single Vite dev server (and later a single tunnel)
serves both halves. See `docs/PILOT.md`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.api import mapping
from src.api.call_fixture import prompts_as_dicts
from src.api.schemas import (
    AgentEventOut,
    CallScriptOut,
    CallTickOut,
    ConsentIn,
    ConsentOut,
    ContinuityBriefOut,
    ConversationPromptOut,
    DatePathOut,
    DatePlanOut,
    DateStopOut,
    EncounterCardOut,
    ExtractIn,
    GuardianCheckInIn,
    GuardianCheckInOut,
    ExtractionOut,
    HealthOut,
    LockInOut,
    RespondIn,
)
from src.agents.date import DateAgent
from src.agents.guardian import GuardianAgent, IncidentLog
from src.agents.onboarding import OnboardingAgent
from src.api.session import (
    EncounterClosed,
    EncounterNotFound,
    GateNotPending,
    SparkSession,
    get_session,
    reset_session,
)
from src.config import SETTINGS
from src.mcp.services import WORLD
from src.safety.consent import build_reveal, reveal_permitted
from src.schemas.core import EncounterState, LockIn

router = APIRouter(prefix="/api")

#: What the intake span is labelled with. NOT a user: there is no auth yet
#: (docs/PILOT.md §8.4), nothing is persisted, and a real id here would imply a
#: durable profile that does not exist.
_INTAKE_SPAN_USER = "demo-intake"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthOut, response_model_by_alias=True)
def health() -> HealthOut:
    """What the pilot runbook checks first.

    Reports the provider, so a deterministic-policy run can never be mistaken
    for a model run — the same discipline the metrics reports follow.
    """
    session = get_session()
    return HealthOut(
        ok=True,
        provider=SETTINGS.model.provider,
        model_reasoning=SETTINGS.model.model_id("reasoning"),
        model_fast=SETTINGS.model.model_id("fast"),
        call_seconds=SETTINGS.rules.call_seconds,
        world_users=len(WORLD.users),
    )


# ---------------------------------------------------------------------------
# The encounter
# ---------------------------------------------------------------------------


@router.post(
    "/encounters", response_model=EncounterCardOut, response_model_by_alias=True
)
def open_encounter() -> EncounterCardOut:
    """Today's encounter. Runs the graph to the accept gate and halts there.

    A 409 means nobody eligible crossed this user's path today. That is a quiet
    day, not a failure — the client shows the empty home screen.
    """
    session = get_session()
    encounter, _result = session.open_encounter()

    if encounter.state is EncounterState.ABANDONED:
        raise HTTPException(
            status_code=409,
            detail=(
                "No eligible candidate crossed your path today. This is a "
                "normal outcome, not an error — the overlap pool did not "
                "survive the intent, language, availability or cooldown rules."
            ),
        )

    return _card_for(session, encounter.id)


@router.get(
    "/encounters/{encounter_id}",
    response_model=EncounterCardOut,
    response_model_by_alias=True,
)
def get_encounter(encounter_id: str) -> EncounterCardOut:
    return _card_for(get_session(), encounter_id)


@router.post("/encounters/{encounter_id}/respond")
def respond(encounter_id: str, body: RespondIn) -> dict:
    """Answer the notification. Resumes the accept gate.

    A decline and a no-show both end ABANDONED, and this returns the same
    payload for both — INVARIANT 2. The client's close-out takes no props, so
    it could not vary even if this told it something.
    """
    session = get_session()
    result = session.accept(encounter_id, viewer_yes=body.accept)
    encounter = result["encounter"]
    connected = encounter.state is not EncounterState.ABANDONED
    return {"connected": connected, "state": "CONNECTED" if connected else "ABANDONED"}


@router.get(
    "/encounters/{encounter_id}/call-script",
    response_model=CallScriptOut,
    response_model_by_alias=True,
)
def call_script(encounter_id: str) -> CallScriptOut:
    """The audio track for the call.

    STUBBED, and stated as such rather than quietly faked. The voice bridge is a
    mock (`spark-voice`), so this returns the same scripted amplitude track the
    client's MockAdapter uses. When LiveKit lands, the amplitude comes from the
    real track and this endpoint returns prompts only.

    The 180-second stop does NOT depend on this: it is enforced in
    `spark-voice.connect_call`, where duration is not a parameter.
    """
    session = get_session()
    encounter = session.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=404, detail=f"no encounter {encounter_id}")

    ticks, prompts = _scripted_call(SETTINGS.rules.call_seconds)
    return CallScriptOut(
        ticks=[CallTickOut(**t) for t in ticks],
        prompts=[ConversationPromptOut(**p) for p in prompts],
    )


@router.post(
    "/encounters/{encounter_id}/consent",
    response_model=ConsentOut,
    response_model_by_alias=True,
)
def consent(encounter_id: str, body: ConsentIn) -> ConsentOut:
    """The post-call gate. Resumes the reveal interrupt.

    This function does not decide the outcome. It resumes the graph, and then
    asks `src/safety/consent.py` whether a reveal is permitted — the same
    function `tests/test_consent.py` exercises across all nine combinations of
    two answers.

    INVARIANT 3 at the boundary: on every non-mutual ending the payload is
    `{"outcome": ..., "person": null}` and is otherwise identical. The outcome
    label exists so the demo controls can film each branch; the client renders
    a close-out that takes no props, so it cannot use it.
    """
    session = get_session()

    # A closed encounter answers like every other non-connection: same shape,
    # same absent person. INVARIANT 3 — the payload must not tell anyone which
    # branch they are on, and "closed for safety" is not an exception to that.
    if session.guardian_closed(encounter_id):
        session.require_encounter(encounter_id)      # 404 for an unknown id
        return ConsentOut(outcome="declined", person=None)

    result = session.consent(encounter_id, viewer_yes=body.yes)
    encounter = result["encounter"]

    if not session.reveal_allowed(encounter):
        # No identity is built, and none exists to leak. `declined` vs
        # `no_response` is a label for the operator, never a difference the
        # user can see.
        # The label distinguishes "I said no" from "they did not say yes" so the
        # demo controls can film both. The PAYLOAD is otherwise identical, and
        # the client's close-out takes no props, so it cannot use the label.
        return ConsentOut(
            outcome="declined" if not body.yes else "no_response", person=None
        )

    viewer = session.user(encounter.user_a)
    peer = session.user(encounter.user_b)
    view = build_reveal(
        session.ledger,
        encounter,
        viewer_id=viewer.id,
        other=peer,
        lockin_id=result.get("lockin_id", ""),
        at=encounter.call_ended or datetime.now(),
    )
    shared = sorted(set(viewer.profile.interests) & set(peer.profile.interests))
    return ConsentOut(outcome="mutual", person=mapping.reveal_out(view, peer, shared))


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


@router.post(
    "/onboarding/extract",
    response_model=ExtractionOut,
    response_model_by_alias=True,
)
def onboarding_extract(body: ExtractIn) -> ExtractionOut:
    """One turn of conversational intake, run by the real Onboarding Agent.

    This is the same `OnboardingAgent` the simulation and the evaluation use —
    the model call, the Trust & Safety screen on the intake text, and the
    intent rule that runs afterwards in ordinary Python. There is no second,
    friendlier extractor behind the demo.

    The rule worth being explicit about: `_enforce_rules` drops any intent the
    transcript did not NAME, whatever the model returned. So a warm sentence
    comes back with `unresolved: ["intent"]` and the client asks, rather than
    someone being matched under a reading of their tone.

    No auth yet (docs/PILOT.md §8.4), so this extracts for the demo user and
    persists nothing. Intake is client-side state until there is a user to
    attach it to.
    """
    agent = OnboardingAgent(trust=get_session().runtime.trust)
    extraction = agent.extract(_INTAKE_SPAN_USER, body.transcript)
    return ExtractionOut(
        intents=[i.value for i in extraction.intents],
        interests=list(extraction.interests),
        values=list(extraction.values),
        availability=[b.value for b in extraction.availability_window],
        languages=list(extraction.languages),
        unresolved=list(extraction.unresolved),
        follow_up=agent.follow_up_question(extraction),
    )


# ---------------------------------------------------------------------------
# Guardian
# ---------------------------------------------------------------------------

#: One log for the process, append-only.
#:
#: Separate from the consent ledger and never joined to it: an incident is an
#: operational safety record, a consent event is a person's decision. Mixing
#: them would make both harder to reason about, and the second one is load
#: bearing for invariant 5.
INCIDENTS = IncidentLog()


@router.post(
    "/encounters/{encounter_id}/guardian/check-in",
    response_model=GuardianCheckInOut,
    response_model_by_alias=True,
)
def guardian_check_in(
    encounter_id: str, body: GuardianCheckInIn
) -> GuardianCheckInOut:
    """Record the answer to Guardian's private check-in.

    Until now this went nowhere. The client had a check-in whose two answers did
    different things on screen, and a `GuardianAgent` with an `IncidentLog`
    sitting in `src/agents/` with its own tests — and nothing connecting them.
    A safety feature that appears to listen and does not is worse than one that
    is absent, so this is the wire between them.

    WHAT IT DOES NOT CLAIM. Nothing here notifies a human, and the response says
    so. In this MVP the log is in memory and no operator is watching it; what an
    organisation should do with an entry is a policy question the README states
    rather than pretends to answer. The message is worded to be true today.

    INVARIANT 2: the other party is never told that this was used, or that the
    call ended early. Nothing in this route touches their side.
    """
    session = get_session()
    encounter = session.require_encounter(encounter_id)
    viewer_id = encounter.user_a

    if not body.all_right:
        # CLOSE FIRST, TELL THEM SECOND. If this write fails the exception
        # propagates and the person is not told anything was closed — the
        # message below is only ever sent after the closure has succeeded.
        # Idempotent, so a repeated submission cannot weaken it.
        session.close_for_guardian(encounter_id)

    agent = GuardianAgent(log=INCIDENTS)
    # `answered` is whether the person RESPONDED to the check-in, not whether
    # they were all right. Reaching this route means they pressed a button, so
    # it is always true here; an unanswered check-in is a timeout, and the
    # agent's docstring is explicit that the silence is itself the signal.
    # Passing `all_right` here logged "NO ANSWER — escalate" for someone who
    # had just answered, which is exactly the record an operator must be able
    # to trust.
    agent.record_check_in(
        viewer_id,
        encounter.call_ended or datetime.now(),
        answered=True,
    )
    if not body.all_right:
        # The concern itself, distinct from the fact that they answered.
        INCIDENTS.record(
            viewer_id,
            "concern",
            encounter.call_ended or datetime.now(),
            detail=f"encounter {encounter_id}; reveal withheld",
        )

    return GuardianCheckInOut(
        recorded=True,
        message=(
            "Thank you. We have recorded this privately and closed the "
            "encounter — you will not be asked whether you want to swap names."
            if not body.all_right
            else "Thank you. Nothing about this is shared with the other person."
        ),
    )


# ---------------------------------------------------------------------------
# Date planning
# ---------------------------------------------------------------------------


@router.get(
    "/encounters/{encounter_id}/dates",
    response_model=DatePlanOut,
    response_model_by_alias=True,
)
def date_plan(encounter_id: str) -> DatePlanOut:
    """Three evenings for a pair who have already exchanged names.

    GATED ON THE REVEAL, and that gate is the whole reason this endpoint is
    allowed to point somewhere at all. Invariant 3 forbids rendering a place;
    two people who have mutually said yes and are choosing where to meet are
    picking a destination together, which is a different thing from disclosing
    where either of them was.

    `reveal_permitted` is the same function the consent endpoint uses — the
    check is not re-implemented here, so it cannot drift from the one that
    guards identity.

    Note what the planner is never given: a cell, a coordinate, a distance, or
    either person's overlap history. It ranks on shared interests and time of
    day. A venue search that took a location would become "near where you both
    were", which is precisely what this product removed.

    Hung off the ENCOUNTER rather than the lock-in because `/api/lockins` is
    still stubbed (docs/PILOT.md §6); when the lock-in store moves behind the
    API this becomes `/lockins/{id}/dates` and the body does not change.
    """
    session = get_session()
    encounter = session.require_encounter(encounter_id)

    # `reveal_allowed` covers both the consent check and the safety closure.
    # Planning a date for someone who has just told Guardian that something
    # felt off is the single worst thing this endpoint could do.
    if not session.reveal_allowed(encounter):
        raise HTTPException(
            status_code=409,
            detail=(
                "Date planning opens after you have both said yes and "
                "exchanged names. Answer the reveal gate first: POST "
                f"/api/encounters/{encounter_id}/consent."
            ),
        )

    viewer = session.user(encounter.user_a)
    peer = session.user(encounter.user_b)
    lockin = LockIn(
        id=f"lock-{encounter.id}",
        pair_id=encounter.match_id,
        user_a=viewer.id,
        user_b=peer.id,
        opened_at=encounter.call_ended or datetime.now(),
        last_contact=encounter.call_ended or datetime.now(),
    )

    plan = DateAgent(client=session.runtime.client).plan(lockin, viewer, peer)
    return DatePlanOut(
        paths=[
            DatePathOut(
                path_id=path.path_id,
                headline=path.headline,
                stops=[
                    DateStopOut(
                        venue_id=stop.venue_id,
                        activity=stop.activity,
                        category=stop.category,
                        is_commercial_partner=stop.is_commercial_partner,
                    )
                    for stop in path.stops
                ],
                grounded_in=list(path.grounded_in),
                rationale=path.rationale,
                proposed_bucket=path.proposed_bucket.value,
            )
            for path in plan.paths
        ],
        note=plan.note,
    )


# ---------------------------------------------------------------------------
# Afterwards
# ---------------------------------------------------------------------------


@router.get("/lockins", response_model=list[LockInOut], response_model_by_alias=True)
def lockins() -> list[LockInOut]:
    """The connections open in this run.

    No longer stubbed. A `LockIn` carries a NAME, so the only thing that opens
    one is a mutual reveal — `SparkSession._open_lockin_if_revealed` gates on
    `reveal_permitted`, the same function that guards the identity itself. This
    route reads that store and adds nothing.
    """
    session = get_session()
    out: list[LockInOut] = []
    for lockin in session.lockins():
        viewer_id = session.viewer_id(lockin)
        other = session.user(lockin.other(viewer_id))
        viewer = session.user(viewer_id)
        shared = sorted(set(viewer.profile.interests) & set(other.profile.interests))
        out.append(
            LockInOut(
                lock_in_id=lockin.id,
                person=mapping.reveal_out_from_user(other, shared),
                opened_at=lockin.opened_at.isoformat(),
                last_contact_at=lockin.last_contact.isoformat(),
                state=lockin.state.value,
            )
        )
    return out


@router.get(
    "/briefs", response_model=list[ContinuityBriefOut], response_model_by_alias=True
)
def briefs() -> list[ContinuityBriefOut]:
    """What the Continuity Agent would surface before the next contact.

    Produced by the real agent, from notes written when the lock-in opened. It
    returns `None` when there is nothing to cite, and those are dropped rather
    than padded: a brief with nothing behind it is a reminder, and the product
    already has enough of those.

    The week is derived from the demo clock, so `POST /api/demo/advance-days`
    visibly changes what a brief says — which is the whole "adapts over time"
    claim, and it has to be demonstrable rather than asserted.
    """
    session = get_session()
    now = session.clock.at(9, 0)
    week = session.day_offset_extra // 7 + 1

    out: list[ContinuityBriefOut] = []
    for lockin in session.lockins():
        viewer = session.user(session.viewer_id(lockin))
        brief = session.runtime.continuity.brief(lockin, viewer, week, now)
        if brief is None:
            continue
        out.append(
            ContinuityBriefOut(
                lock_in_id=lockin.id,
                line=brief.message,
                suggested_action=(
                    "Suggest meeting" if week >= 5 else "Ask how it went"
                ),
                source_encounter_id=lockin.id,
            )
        )
    return out


@router.post("/demo/advance-days")
def demo_advance_days(days: int = 1) -> dict:
    """Move the simulated clock forward (FRONTEND.md §8).

    Six weeks of continuity has to fit inside five minutes. This is the control
    that makes the difference between a week-one brief and a week-five one
    visible on camera, and it drives the REAL Continuity Agent rather than
    swapping in different copy.
    """
    session = get_session()
    total = session.advance_days(days)
    return {"advancedBy": days, "dayOffset": total}


@router.get("/events")
async def events() -> StreamingResponse:
    """The Director panel's feed, over Server-Sent Events.

    Streams the spans the agents actually emitted, so what the panel shows is
    the trace rather than a scripted animation of one.
    """
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_stream() -> AsyncIterator[str]:
    """The Director panel's feed.

    TWO THINGS THIS DELIBERATELY DOES NOT DO.

    It does not replay the whole accumulated trace to a new connection. It used
    to, so every reconnect — and the client reconnects on reset — refilled the
    panel with the previous take's rows on top of the new one.

    It does not emit the starter search. `_first_user_with_a_candidate` probes
    users until it finds one whose day goes somewhere, and each probe emitted an
    identical `overlap_pool` tool span. The panel opened with a wall of ten
    near-identical rows before anything interesting happened — the first thing a
    judge sees, and the least interesting ten lines in the run.

    Consecutive duplicates are collapsed for the same reason: a repeated row is
    noise, and the panel's value is that every line means something.
    """
    from src.telemetry.trace import TRACES, is_internal

    # Start from what has ALREADY happened, so a new connection begins with the
    # panel empty and fills as the run proceeds.
    sent = len(TRACES.spans)
    last_row: tuple[str, str] | None = None

    while True:
        spans = TRACES.spans
        while sent < len(spans):
            span = spans[sent]
            sent += 1
            if is_internal(span):
                # Demo machinery, not agent work. Still in the trace file.
                continue
            event = _span_to_event(span)
            if event is None:
                continue
            row = (event.agent, event.action)
            if row == last_row:
                # The same agent doing the same thing again, back to back.
                continue
            last_row = row
            yield f"data: {json.dumps(event.model_dump(by_alias=True))}\n\n"
        await asyncio.sleep(0.25)


#: Which agent owns each MCP server, so a tool call is attributed to the agent
#: that made it rather than all landing on one.
_SERVER_AGENT = {
    "spark-overlap": "match",
    "spark-profile": "continuity",
    "spark-voice": "delivery",
    "spark-calendar": "delivery",
    "spark-venue": "date",
    "spark-sim": "match",
}

#: Span name -> the sentence a person reads. FRONTEND.md §6 wants rows like
#: "match · selected candidate", not "node.select".
_ACTION_LABELS = {
    "node.pool": "pooled today's overlap",
    "node.select": "selected candidate",
    "node.notify": "notified both parties",
    "node.accept_gate": "accept gate",
    "node.call": "opened the bridge",
    "node.consent_gate": "consent gate",
    "node.outcome": "decided the outcome",
    "node.lockin": "lock-in opened",
    "agent.match": "chose who is worth three minutes",
    "agent.continuity": "looked after a lock-in",
    "agent.onboarding": "read the intake",
    "agent.communication": "suggested a grounded prompt",
    "agent.date": "proposed something specific",
    "agent.guardian": "guardian",
    "trust.screen": "screened text",
    "delivery.card": "built an anonymous card",
    "delivery.connect": "connected the call",
    "delivery.outcome": "reveal or close",
}

_NODE_AGENT = {
    "node.pool": "match",
    "node.select": "match",
    "node.notify": "delivery",
    "node.accept_gate": "delivery",
    "node.call": "delivery",
    "node.consent_gate": "delivery",
    "node.outcome": "delivery",
    "node.lockin": "continuity",
    "delivery.card": "delivery",
    "delivery.connect": "delivery",
    "delivery.outcome": "delivery",
    "trust.screen": "safety",
}


#: Spans that are machinery rather than agent work. The starter search is the
#: demo choosing whose day to follow; it is not something an agent decided, and
#: ten identical rows of it is the worst possible opening for the panel.
_INTERNAL_SPANS = frozenset({"demo.starter_search"})


def _span_to_event(span) -> AgentEventOut | None:
    """Turn an OTEL span into a Director row, or drop it.

    Attribution matters here. An `mcp.spark-overlap.*` call is the MATCH agent
    reaching for a tool, not the delivery agent — sending every tool call to one
    row would bury the rows worth reading under a flood of identical ones.
    """
    name = span.name
    attrs = span.attributes or {}

    if name.startswith("agent."):
        agent = name.split(".", 1)[1]
        action = _ACTION_LABELS.get(name, name)
    elif name.startswith("mcp."):
        parts = name.split(".")
        server = parts[1] if len(parts) > 2 else ""
        agent = _SERVER_AGENT.get(server, "delivery")
        action = f"tool · {parts[-1]}"
    elif name in _NODE_AGENT:
        agent = _NODE_AGENT[name]
        action = _ACTION_LABELS.get(name, name)
    else:
        # The graph's own plumbing. Dropped rather than shown.
        return None

    known = {
        "onboarding", "match", "delivery", "continuity",
        "communication", "date", "guardian", "safety",
    }
    if agent not in known:
        return None

    # The rationale the agent returned, which is what §6's collapsible row is
    # for. Loop bookkeeping and the duration are already columns.
    detail = ", ".join(
        f"{k}={v}"
        for k, v in sorted(attrs.items())
        if k != "duration_ms" and not k.startswith("loop.")
    )

    return AgentEventOut(
        ts=datetime.now().isoformat(),
        agent=agent,                                     # type: ignore[arg-type]
        action=action,
        detail=detail[:240],
        duration_ms=max(1, int(span.duration_ms)),
        status="ok" if span.status != "ERROR" else "error",
    )


# ---------------------------------------------------------------------------
# Demo controls (§8)
# ---------------------------------------------------------------------------


class ForceOutcomeIn(BaseModel):
    """§8's "force outcome", so each branch can be filmed.

    Sets what the SIMULATED OTHER PARTY does. It does not change what the viewer
    sees for a given pair of answers — that is the thing invariant 3 protects,
    and this control cannot reach it.
    """

    outcome: Literal["mutual", "declined", "no_response"]


@router.post("/demo/force-outcome")
def demo_force_outcome(body: ForceOutcomeIn) -> dict:
    session = get_session()
    # `declined` and `no_response` both mean "the other party did not say yes".
    # They are the same instruction to the graph, and deliberately so: the two
    # are indistinguishable downstream, which is the invariant.
    session.forced_peer_answer = body.outcome == "mutual"
    return {"ok": True, "outcome": body.outcome}


@router.post("/demo/reset")
def demo_reset(seed: int | None = None) -> dict:
    """Deterministic reset. Same seed, same take."""
    session = reset_session(seed)
    return {"ok": True, "seed": session.seed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _card_for(session: SparkSession, encounter_id: str) -> EncounterCardOut:
    # `require_encounter`, not `get`: it falls back to the durable checkpoint, so a card
    # can still be fetched after the server restarted mid-encounter. Raises
    # EncounterNotFound, which the handler below turns into a 404.
    encounter = session.require_encounter(encounter_id)
    viewer = session.user(encounter.user_a)
    peer = session.user(encounter.user_b)
    return mapping.encounter_card_out(
        encounter,
        viewer,
        peer,
        shared_bucket=session.shared_bucket(viewer.id, peer.id),
        window_closes_at=session.window_closes_at().isoformat(),
        call_seconds=SETTINGS.rules.call_seconds,
    )


def _scripted_call(seconds: int) -> tuple[list[dict], list[dict]]:
    """The mock amplitude track. Mirrors `web/src/api/mock.ts` so the two
    adapters produce the same call."""
    import random

    rng = random.Random(SETTINGS.sim.seed + 1009)
    stalls = [(46, 54), (118, 126)]
    ticks: list[dict] = []
    for elapsed in range(seconds + 1):
        in_stall = any(a <= elapsed <= b for a, b in stalls)
        if in_stall:
            speaker = "silence"
        elif elapsed < 8:
            speaker = "remote"
        else:
            speaker = "local" if (elapsed // 7) % 2 == 0 else "remote"

        if speaker == "silence":
            amplitude = 0.04 + rng.random() * 0.05
        else:
            import math

            envelope = 0.45 + 0.35 * math.sin(elapsed / 2.7)
            amplitude = min(1.0, max(0.08, envelope + (rng.random() - 0.5) * 0.3))
            if elapsed > 150:
                amplitude *= 1 - (elapsed - 150) / 60
        ticks.append(
            {"elapsed": elapsed, "amplitude": round(amplitude, 4), "speaker": speaker}
        )

    return ticks, prompts_as_dicts()


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Spark",
        version="0.1.0",
        description=(
            "The HTTP layer over the Spark supervisor graph. The consent gates "
            "reached here are the same LangGraph interrupt() calls the CLI and "
            "the evaluation drive."
        ),
    )
    # The phone reaches this through the Vite dev server's /api proxy, so same
    # origin in practice. CORS is permissive because this is a demo server that
    # holds no real data and is never deployed — stated here so the choice is
    # visible rather than assumed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ---------------------------------------------------------------
    # Domain errors -> status codes, in one place
    # ---------------------------------------------------------------
    #
    # Registered as handlers rather than repeated as try/except in every route,
    # so a route added later cannot forget one and return a 500 — which for
    # GateNotPending would look like a server fault rather than a refusal.

    @app.exception_handler(EncounterNotFound)
    async def _not_found(_request: Request, exc: EncounterNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(EncounterClosed)
    async def _closed(_request: Request, exc: EncounterClosed) -> JSONResponse:
        # 409: the request is well formed, the encounter is simply over.
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(GateNotPending)
    async def _out_of_order(_request: Request, exc: GateNotPending) -> JSONResponse:
        # 409, not 400: the request is well formed, it is the CONVERSATION that
        # is in the wrong state. The message says which gate is actually
        # pending and what to call, because "conflict" alone is not actionable.
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
