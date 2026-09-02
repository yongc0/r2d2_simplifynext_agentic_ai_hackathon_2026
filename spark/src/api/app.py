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
import re
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
    DateFeedbackIn,
    DateMemoryOut,
    DateMemoryPatchIn,
    DatePathOut,
    DatePlanOut,
    DatePreferencesIn,
    DatePreferencesOut,
    DateStopOut,
    EncounterCardOut,
    ExtractIn,
    GuardianCheckInIn,
    GuardianCheckInOut,
    ExtractionOut,
    HealthOut,
    ItineraryOut,
    ItineraryResultOut,
    ItineraryStatusIn,
    ItineraryStopOut,
    LockInOut,
    PlacesStatusOut,
    PlanLockInOut,
    ProfileIn,
    ProfileOut,
    ReflectionIn,
    ReflectionOut,
    RespondIn,
    SettingsIn,
    SettingsOut,
    TravelLegOut,
)
from src.agents.date import DateAgent
from src.agents.itinerary import ItineraryAgent, NoItinerary
from src.agents.guardian import GuardianAgent, IncidentLog
from src.agents.onboarding import OnboardingAgent, _KNOWN_TRAITS
from src.api.session import (
    UNKNOWN_LOCKIN,
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
from src.schemas.core import EncounterState, Intent, LockIn, TimeBucket
from src.schemas.date_studio import (
    DatePlanFeedback,
    DatePlanningPreferences,
    DatePlanRecord,
)
from src.schemas.itinerary import USER_SETTABLE_STATUSES, DateItinerary

router = APIRouter(prefix="/api")

#: What the intake span is labelled with. NOT a user: there is no auth yet
#: (docs/PILOT.md §8.4), this extraction call itself persists nothing, and a
#: real id here would imply the transcript is already attached to an account.
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

    No auth yet (docs/PILOT.md §8.4), so this extraction call does not persist
    the transcript. Once all required topics are present, the client commits the
    structured result through ``PUT /profile``; that updates the same Profile
    object the Match Agent reads without retaining the conversation itself.
    """
    agent = OnboardingAgent(trust=get_session().runtime.trust)
    extraction = agent.extract(_INTAKE_SPAN_USER, body.transcript)
    return ExtractionOut(
        intents=[i.value for i in extraction.intents],
        traits=[
            trait
            for trait in _KNOWN_TRAITS
            if re.search(rf"\b{re.escape(trait)}\b", extraction.personality, re.I)
        ],
        interests=list(extraction.interests),
        values=list(extraction.values),
        availability=[b.value for b in extraction.availability_window],
        languages=list(extraction.languages),
        unresolved=list(extraction.unresolved),
        follow_up=agent.follow_up_question(extraction),
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _viewer_scope(session: SparkSession):
    """The consent scope the settings screen reads and writes.

    With no auth the viewer is whoever the demo is following, derived from the
    session rather than taken from the request — the same rule every other
    owner-scoped route follows.
    """
    return session.user(session.viewer_user_id()).consent_scope


def _profile_out(session: SparkSession) -> ProfileOut:
    """This viewer's own profile, plus the buckets they are genuinely ever out in.

    `known_buckets` comes from their overlap history rather than from the full
    enum. Offering "early morning" to somebody who has never once been out then
    invites them to set a window that removes them from every pool — a
    preference screen that can quietly switch the product off is worse than one
    with fewer options.
    """
    user = session.user(session.viewer_user_id())
    seen = session.runtime.client.try_call(
        "spark-calendar",
        "availability",
        default={"buckets": []},
        user_id=user.id,
    ) or {"buckets": []}
    known = list(seen.get("buckets") or [])
    return ProfileOut(
        intents=[i.value for i in user.profile.intents],
        interests=list(user.profile.interests),
        values=list(user.profile.values),
        personality=user.profile.personality,
        lifestyle=user.profile.lifestyle,
        languages=list(user.profile.languages),
        availability_window=[b.value for b in user.profile.availability_window],
        known_buckets=known or [b.value for b in TimeBucket],
    )


@router.get("/profile", response_model=ProfileOut, response_model_by_alias=True)
def get_profile() -> ProfileOut:
    """The viewer's own profile. There is no route that returns anybody else's."""
    return _profile_out(get_session())


@router.put("/profile", response_model=ProfileOut, response_model_by_alias=True)
def put_profile(body: ProfileIn) -> ProfileOut:
    """Change what Spark matches you on.

    NOT A UI-ONLY PREFERENCES PAGE. This writes the same `Profile` object the
    Match Agent reads, so the next encounter is scored against the new values:
    intents gate eligibility, interests drive overlap scoring and ground every
    date plan, and the availability window decides which slots you can be
    offered in at all.

    Validation is strict and the errors say why. An intent outside the vocabulary
    or a time bucket that does not exist is rejected rather than dropped — a
    preference silently discarded is worse than one refused, because the person
    believes it took.
    """
    session = get_session()
    user = session.user(session.viewer_user_id())
    profile = user.profile

    updates: dict[str, object] = {}

    if body.intents is not None:
        if not body.intents:
            # `Profile.intents` has min_length=1, and for a good reason: a
            # person with no stated intent cannot be matched with anybody.
            raise HTTPException(
                status_code=422,
                detail=(
                    "at least one connection intent is required — with none, "
                    "there is nobody you could be matched with"
                ),
            )
        try:
            updates["intents"] = [Intent(value) for value in body.intents]
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"unknown connection intent: {exc}. Valid: "
                f"{[i.value for i in Intent]}",
            ) from exc

    if body.availability_window is not None:
        try:
            updates["availability_window"] = [
                TimeBucket(value) for value in body.availability_window
            ]
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"unknown time bucket: {exc}. Valid: "
                f"{[b.value for b in TimeBucket]}",
            ) from exc

    for field in ("interests", "values", "personality", "lifestyle", "languages"):
        value = getattr(body, field)
        if value is not None:
            updates[field] = value

    if updates:
        # Rebuilt through the model, so the same validators the onboarding path
        # runs — deduplication, casing, length caps — apply to an edit too.
        try:
            user.profile = profile.model_copy(update=updates)
            user.profile = type(profile).model_validate(user.profile.model_dump())
        except Exception as exc:                              # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _profile_out(session)


@router.get("/settings", response_model=SettingsOut, response_model_by_alias=True)
def get_settings() -> SettingsOut:
    scope = _viewer_scope(get_session())
    return SettingsOut(
        allow_calls=scope.allow_calls,
        allow_date_suggestions=scope.allow_date_suggestions,
        allow_continuity_notes=scope.allow_continuity_notes,
        allow_conversation_prompts=scope.allow_conversation_prompts,
    )


@router.put("/settings", response_model=SettingsOut, response_model_by_alias=True)
def put_settings(body: SettingsIn) -> SettingsOut:
    """Change a switch, and mean it.

    These write to `ConsentScope`, which the agents consult before acting —
    `allow_calls` is read by `spark-voice.connect_call` and by the Delivery
    Agent before it even reaches the bridge. Turning a switch off here removes
    a capability rather than hiding a control.

    A partial update: fields omitted are left alone, so one screen toggling one
    switch cannot silently reset the others.
    """
    scope = _viewer_scope(get_session())
    for field in (
        "allow_calls",
        "allow_date_suggestions",
        "allow_continuity_notes",
        "allow_conversation_prompts",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(scope, field, value)
    return get_settings()


# ---------------------------------------------------------------------------
# Date Studio
# ---------------------------------------------------------------------------
#
# THE VIEWER IS ALWAYS DERIVED, NEVER SUPPLIED. Every route below takes its
# owner from the lock-in the server already holds. A client that could name the
# owner of a memory item could read and rewrite somebody else's preferences,
# and there is no auth here to stop it — so the id simply never crosses the
# wire in that direction.


def _planning_lockin(session: SparkSession, lockin_id: str):
    """The lock-in, if planning is permitted on it. Raises otherwise.

    404 for a lock-in that does not exist, 409 when it exists but planning is
    not open — released, closed by Guardian, or date suggestions turned off.
    One helper so every route refuses identically; the reasons live in
    `SparkSession.planning_refusal`.
    """
    refusal = session.planning_refusal(lockin_id)
    if refusal == UNKNOWN_LOCKIN:
        raise HTTPException(status_code=404, detail=f"no lock-in {lockin_id}")
    if refusal is not None:
        raise HTTPException(status_code=409, detail=refusal)
    return session.lockin(lockin_id)


@router.get("/plans", response_model=list[PlanLockInOut], response_model_by_alias=True)
def plan_hub() -> list[PlanLockInOut]:
    """Connections you can plan with.

    Only lock-ins, so only pairs who have already exchanged names. A connection
    that cannot be planned with is still listed, with the reason — hiding it
    would leave someone wondering where a person went.
    """
    session = get_session()
    out: list[PlanLockInOut] = []
    for lockin in session.lockins():
        viewer_id = session.viewer_id(lockin)
        other = session.user(lockin.other(viewer_id))
        viewer = session.user(viewer_id)
        shared = sorted(set(viewer.profile.interests) & set(other.profile.interests))
        refusal = session.planning_refusal(lockin.id)
        out.append(
            PlanLockInOut(
                lock_in_id=lockin.id,
                person=mapping.reveal_out_from_user(other, shared),
                state=lockin.state.value,
                unavailable_reason=None if refusal is None else refusal,
            )
        )
    return out


@router.get(
    "/lockins/{lockin_id}/date-preferences",
    response_model=DatePreferencesOut,
    response_model_by_alias=True,
)
def get_date_preferences(lockin_id: str) -> DatePreferencesOut:
    """The remembered constraints, and the times they genuinely share.

    `prefilled` is true when these came from memory. The form must SAY it
    prefilled rather than presenting remembered values as though the person had
    just chosen them — a preference someone did not notice being applied is one
    they cannot correct.
    """
    session = get_session()
    lockin = _planning_lockin(session, lockin_id)
    viewer_id = session.viewer_id(lockin)

    remembered = {
        item.dimension: item.value
        for item in session.date_memory.for_owner(viewer_id, lockin_id)
    }
    buckets = session.runtime.client.try_call(
        "spark-calendar", "shared_availability",
        default={"shared_buckets": []},
        user_a=lockin.user_a, user_b=lockin.user_b,
    ) or {"shared_buckets": []}

    return DatePreferencesOut(
        mood=remembered.get("mood"),
        budget=remembered.get("budget"),
        duration=remembered.get("duration"),
        energy=remembered.get("energy"),
        formats=[remembered["format"]] if "format" in remembered else [],
        time_bucket=None,
        shared_buckets=list(buckets["shared_buckets"]),
        prefilled=bool(remembered),
    )


@router.put(
    "/lockins/{lockin_id}/date-preferences",
    response_model=DatePreferencesOut,
    response_model_by_alias=True,
)
def put_date_preferences(
    lockin_id: str, body: DatePreferencesIn
) -> DatePreferencesOut:
    """Store constraints the person asked to be remembered.

    ONLY when `remember` is true. "I am tired tonight" is context, and a system
    that promotes tonight's mood into a durable belief will be wrong about
    someone forever without ever having been told anything untrue.

    Idempotent: the store upserts one row per (owner, scope, dimension), so
    saving twice updates rather than accumulating.
    """
    session = get_session()
    lockin = _planning_lockin(session, lockin_id)
    viewer_id = session.viewer_id(lockin)

    if body.remember:
        preferences = DatePlanningPreferences(
            mood=body.mood, budget=body.budget, duration=body.duration,
            energy=body.energy, formats=body.formats,
        )
        for dimension, value in preferences.as_pairs():
            session.date_memory.remember(
                owner_id=viewer_id, scope="user", dimension=dimension,
                value=value, source="explicit",
            )
    return get_date_preferences(lockin_id)


@router.post(
    "/lockins/{lockin_id}/date-plans",
    response_model=DatePlanOut,
    response_model_by_alias=True,
)
def create_date_plans(lockin_id: str, body: DatePreferencesIn) -> DatePlanOut:
    """Three plans, ranked from this request and what is remembered.

    The request's time bucket is checked against the pair's SHARED availability
    before it reaches the agent: a time only one of them is free is not a
    constraint, it is a plan neither can attend.
    """
    session = get_session()
    lockin = _planning_lockin(session, lockin_id)
    return _plan_out(_studio_plan_for(session, lockin, body))


def _studio_plan_for(session: SparkSession, lockin, body: DatePreferencesIn):
    """Rank three plans for this pair, and snapshot what was shown.

    Extracted so `POST /date-plans` and `POST /itineraries` share one planner
    rather than two that drift. Both need the same three things: the remembered
    preferences applied, the feedback history applied, and every offered plan
    recorded — without that last step a client could later submit feedback for a
    plan that was never offered, and the memory would fill with beliefs derived
    from nothing.
    """
    viewer_id = session.viewer_id(lockin)
    viewer = session.user(viewer_id)
    peer = session.user(lockin.other(viewer_id))

    if body.remember:
        put_date_preferences(lockin.id, body)

    preferences = DatePlanningPreferences(
        mood=body.mood, budget=body.budget, duration=body.duration,
        energy=body.energy, formats=body.formats, time_bucket=body.time_bucket,
    )
    memory = session.date_memory.for_owner(viewer_id, lockin.id)
    feedback = session.date_memory.feedback_for(viewer_id, lockin.id)

    seen_leads = set()
    saved_shapes = set()
    for entry in feedback:
        record = session.date_memory.get_plan(entry.plan_id)
        if record is None:
            continue
        if entry.action == "rejected":
            seen_leads.add(record.lead_venue_id)
        if entry.action in ("saved", "completed"):
            saved_shapes.add(record.shape)

    plan = DateAgent(client=session.runtime.client).studio_plan(
        lockin, viewer, peer, preferences, memory, feedback,
        seen_leads=seen_leads, saved_shapes=saved_shapes,
    )

    now = datetime.now()
    for path in plan.paths:
        session.date_memory.record_plan(
            DatePlanRecord(
                plan_id=path.path_id, lockin_id=lockin.id, owner_id=viewer_id,
                shape=path.shape, lead_venue_id=path.stops[0].venue_id,
                budget_band=path.budget_band, duration_band=path.duration_band,
                energy_band="medium",
                formats=[], created_at=now,
            )
        )
    return plan


@router.post("/date-plans/{plan_id}/feedback")
def date_plan_feedback(plan_id: str, body: DateFeedbackIn) -> dict:
    """What someone did with a plan.

    Validated against a STORED plan belonging to this viewer and lock-in: a
    client cannot submit feedback for something that was never offered, or for
    somebody else's plan.

    Idempotent. The store deactivates previous rows for the same (plan, owner)
    before inserting, so a double-tap does not double-learn and changing your
    mind leaves one active answer with the old one still readable.
    """
    session = get_session()
    record = session.date_memory.get_plan(plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no plan {plan_id}")

    lockin = _planning_lockin(session, record.lockin_id)
    viewer_id = session.viewer_id(lockin)
    if record.owner_id != viewer_id:
        # Not 403: saying "that is not yours" confirms it exists.
        raise HTTPException(status_code=404, detail=f"no plan {plan_id}")

    session.date_memory.record_feedback(
        DatePlanFeedback(
            feedback_id=f"fb:{plan_id}:{viewer_id}",
            plan_id=plan_id, lockin_id=record.lockin_id, owner_id=viewer_id,
            action=body.action, reasons=body.reasons, created_at=datetime.now(),
        )
    )

    # A rejection with a reason is the one signal that becomes a belief, and
    # only ever a lock-in scoped one: a reaction to one person is not a fact
    # about somebody in general.
    learned = 0
    if body.action == "rejected":
        for reason in body.reasons:
            value = _REASON_LEARNS.get(reason)
            if value is None:
                continue
            dimension, learn = value
            session.date_memory.remember(
                owner_id=viewer_id, scope="lockin", lockin_id=record.lockin_id,
                dimension=dimension, value=learn, source="feedback",
            )
            learned += 1
    return {"recorded": True, "learned": learned}


#: A rejection reason -> the belief it argues for. Only reasons that name a
#: DIMENSION appear: `not_our_style` and `already_done` are recorded but teach
#: nothing, because neither says what was wrong and guessing would be inventing
#: a preference from a shrug.
_REASON_LEARNS: dict[str, tuple[str, str]] = {
    "too_expensive": ("budget", "free"),
    "too_long": ("duration", "one_hour"),
    "too_active": ("energy", "low"),
    "too_quiet": ("energy", "high"),
    "too_crowded": ("format", "outdoors"),
}


@router.get(
    "/date-memory", response_model=list[DateMemoryOut], response_model_by_alias=True
)
def date_memory(lockInId: str | None = None) -> list[DateMemoryOut]:
    """What Spark remembers about this viewer.

    Scoped to the viewer by the server. Another person's memory is not
    addressable from here, because the owner is never taken from the request.
    """
    session = get_session()
    lockins = session.lockins()
    if not lockins:
        return []
    viewer_id = session.viewer_id(lockins[0])
    return [
        DateMemoryOut(
            memory_id=item.memory_id, scope=item.scope, lockin_id=item.lockin_id,
            dimension=item.dimension, value=item.value, source=item.source,
            confidence=round(item.confidence, 2),
            updated_at=item.updated_at.isoformat(),
        )
        for item in session.date_memory.for_owner(viewer_id, lockInId)
    ]


@router.patch(
    "/date-memory/{memory_id}",
    response_model=DateMemoryOut,
    response_model_by_alias=True,
)
def correct_date_memory(memory_id: str, body: DateMemoryPatchIn) -> DateMemoryOut:
    """The person fixing what Spark believes.

    A correction is explicit by definition and takes explicit confidence: having
    been told, Spark should stop weighing what it had inferred.
    """
    session = get_session()
    lockins = session.lockins()
    if not lockins:
        raise HTTPException(status_code=404, detail=f"no memory {memory_id}")
    viewer_id = session.viewer_id(lockins[0])

    item = session.date_memory.correct(memory_id, viewer_id, body.value)
    if item is None:
        raise HTTPException(status_code=404, detail=f"no memory {memory_id}")
    return DateMemoryOut(
        memory_id=item.memory_id, scope=item.scope, lockin_id=item.lockin_id,
        dimension=item.dimension, value=item.value, source=item.source,
        confidence=round(item.confidence, 2),
        updated_at=item.updated_at.isoformat(),
    )


@router.delete("/date-memory/{memory_id}")
def forget_date_memory(memory_id: str) -> dict:
    """Delete a remembered preference.

    Soft delete, so the audit trail stays readable — but nothing inactive is
    ever scored, so as far as planning is concerned it is gone immediately.
    """
    session = get_session()
    lockins = session.lockins()
    if not lockins:
        raise HTTPException(status_code=404, detail=f"no memory {memory_id}")
    viewer_id = session.viewer_id(lockins[0])
    if not session.date_memory.forget(memory_id, viewer_id):
        raise HTTPException(status_code=404, detail=f"no memory {memory_id}")
    return {"deleted": True}


def _plan_out(plan) -> DatePlanOut:
    """One mapping from agent plan to wire, shared by both date endpoints."""
    return DatePlanOut(
        paths=[
            DatePathOut(
                path_id=path.path_id,
                headline=path.headline,
                stops=[
                    DateStopOut(
                        venue_id=stop.venue_id, activity=stop.activity,
                        category=stop.category,
                        is_commercial_partner=stop.is_commercial_partner,
                    )
                    for stop in path.stops
                ],
                grounded_in=list(path.grounded_in),
                rationale=path.rationale,
                proposed_bucket=path.proposed_bucket.value,
                shape=path.shape,
                budget_band=path.budget_band,
                duration_band=path.duration_band,
            )
            for path in plan.paths
        ],
        note=plan.note,
    )


# ---------------------------------------------------------------------------
# Itineraries — the plan with real venues, times and a route
# ---------------------------------------------------------------------------
#
# The only routes in the API that return a coordinate, and they are safe for the
# reason ARCHITECTURE §13.6 gives: they run on a LOCK-IN, which exists only
# after a mutual reveal, and the catalogue behind them is never told where
# either person has been. A destination two people chose together is not a
# disclosure of where either of them was.
#
# Every route derives the owner from the session. None accepts an owner id.


def _itinerary_out(session: SparkSession, itinerary: DateItinerary) -> ItineraryOut:
    """One plan, as the client sees it.

    `has_reflection` is THIS viewer's own. There is deliberately no field for
    whether the other person wrote one: that fact is itself a signal, and a
    screen that showed it would let somebody infer an answer they were never
    meant to see.
    """
    return ItineraryOut(
        itinerary_id=itinerary.itinerary_id,
        lock_in_id=itinerary.lockin_id,
        path_id=itinerary.path_id,
        headline=itinerary.headline,
        time_bucket=itinerary.time_bucket.value,
        day_label=itinerary.day_label,
        stops=[
            ItineraryStopOut(
                stop_id=stop.stop_id,
                order=stop.order,
                activity_type=stop.activity_type,
                venue_id=stop.venue_id,
                venue_name=stop.venue_name,
                address=stop.address,
                lat=stop.lat,
                lon=stop.lon,
                start_time=stop.start_time,
                end_time=stop.end_time,
                duration_minutes=stop.duration_minutes,
                estimated_cost=stop.estimated_cost,
                cost_band=stop.cost_band,
                rationale=stop.rationale,
                travel_from_previous=(
                    TravelLegOut(
                        minutes=stop.travel_from_previous.minutes,
                        metres=stop.travel_from_previous.metres,
                        mode=stop.travel_from_previous.mode,
                        detail=stop.travel_from_previous.detail,
                    )
                    if stop.travel_from_previous
                    else None
                ),
                maps_url=stop.maps_url,
                opening_state=stop.opening_state,
                opening_hours=stop.opening_hours,
                opening_detail=stop.opening_detail,
                is_commercial_partner=stop.is_commercial_partner,
            )
            for stop in itinerary.stops
        ],
        total_duration_minutes=itinerary.total_duration_minutes,
        total_cost_estimate=itinerary.total_cost_estimate,
        grounded_in=list(itinerary.grounded_in),
        status=itinerary.status,
        note=itinerary.note,
        attribution=itinerary.attribution,
        updated_at=itinerary.updated_at.isoformat(),
        has_reflection=session.itineraries.reflection_for(
            itinerary.itinerary_id, itinerary.owner_id
        )
        is not None,
    )


def _owned_itinerary(session: SparkSession, itinerary_id: str) -> DateItinerary:
    """This viewer's plan, or a 404.

    A plan belonging to somebody else 404s rather than 403s. A 403 would confirm
    that a plan exists under that id, which is a fact about another person's
    evening.
    """
    owner_id = session.viewer_user_id()
    itinerary = session.itineraries.get(itinerary_id, owner_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail=f"no itinerary {itinerary_id}")
    return itinerary


@router.get(
    "/places/status", response_model=PlacesStatusOut, response_model_by_alias=True
)
def places_status() -> PlacesStatusOut:
    """Whether real venue data is loaded.

    Read by the client BEFORE it offers to plan, so "we cannot name places yet"
    is a state the interface enters deliberately rather than an empty list a
    user has to interpret (§12).
    """
    session = get_session()
    state = session.runtime.client.try_call(
        "spark-places",
        "places_available",
        default={
            "available": False,
            "count": 0,
            "with_hours": 0,
            "source": "openstreetmap",
            "attribution": "",
            "note": "",
        },
    )
    return PlacesStatusOut(
        available=bool(state["available"]),
        count=int(state["count"]),
        with_hours=int(state["with_hours"]),
        source=str(state["source"]),
        attribution=str(state["attribution"]),
        note=str(state["note"]),
    )


@router.post(
    "/lockins/{lockin_id}/itineraries",
    response_model=ItineraryResultOut,
    response_model_by_alias=True,
)
def create_itinerary(lockin_id: str, body: DatePreferencesIn) -> ItineraryResultOut:
    """Plan the date: rank the evening, then bind it to real places and times.

    ONE CALL, because this is the "Plan the Date" button and a button that then
    requires the user to pick a path, then a venue, then a time is not a button.
    With no `pathId` the best-ranked plan is used; with one, that plan is bound
    instead, which is how Date Studio turns a chosen option into an itinerary.

    Two agents run here and the order matters. `DateAgent.studio_plan` decides
    the SHAPE from shared interests and remembered preferences, over a catalogue
    with no location field. `ItineraryAgent.build` then binds that shape to real
    venues, from a catalogue that has coordinates and has never been told where
    anybody is. Neither half can see what the other must not.
    """
    session = get_session()
    lockin = _planning_lockin(session, lockin_id)
    viewer_id = session.viewer_id(lockin)

    plan = _studio_plan_for(session, lockin, body)
    if not plan.paths:
        return ItineraryResultOut(
            itinerary=None,
            reason=plan.note or "Nothing that fits you both, at a time you share.",
        )

    chosen = plan.paths[0]
    if body.path_id:
        matched = [p for p in plan.paths if p.path_id == body.path_id]
        if not matched:
            # The offered plans are re-derived per request, so a stale id is an
            # ordinary consequence of changed preferences rather than a fault.
            # Falling back silently would hand somebody a different evening from
            # the one they tapped.
            raise HTTPException(
                status_code=409,
                detail=(
                    "that plan is no longer among the current suggestions — "
                    "generate again and pick one of these"
                ),
            )
        chosen = matched[0]

    result = ItineraryAgent(client=session.runtime.client).build(
        chosen, owner_id=viewer_id, day_label=_day_label(chosen.proposed_bucket.value)
    )
    if isinstance(result, NoItinerary):
        return ItineraryResultOut(
            itinerary=None,
            reason=result.reason,
            data_unavailable=result.data_unavailable,
        )

    saved = session.itineraries.save(result)
    return ItineraryResultOut(itinerary=_itinerary_out(session, saved))


@router.get(
    "/itineraries", response_model=list[ItineraryOut], response_model_by_alias=True
)
def list_itineraries(lockInId: str | None = None) -> list[ItineraryOut]:
    """Date history — this viewer's plans, newest first.

    Every status, including cancelled. A history that hid the dates that did not
    happen would be a highlight reel, and the person already knows.
    """
    session = get_session()
    owner_id = session.viewer_user_id()
    return [
        _itinerary_out(session, itinerary)
        for itinerary in session.itineraries.for_owner(owner_id, lockInId)
    ]


@router.get(
    "/itineraries/{itinerary_id}",
    response_model=ItineraryOut,
    response_model_by_alias=True,
)
def get_itinerary(itinerary_id: str) -> ItineraryOut:
    session = get_session()
    return _itinerary_out(session, _owned_itinerary(session, itinerary_id))


@router.post(
    "/itineraries/{itinerary_id}/stops/{order}/replace",
    response_model=ItineraryResultOut,
    response_model_by_alias=True,
)
def replace_itinerary_stop(itinerary_id: str, order: int) -> ItineraryResultOut:
    """Swap one stop. The others keep their venues; the later ones are re-timed.

    Re-timing is not optional and not a side effect: a different venue is a
    different walk, and a plan whose later times did not move would be a
    schedule that no longer adds up.

    On failure THE STORED PLAN IS UNTOUCHED and the reason is returned alongside
    it. "There is nothing else of that kind open then" must not cost somebody
    the plan they already had.
    """
    session = get_session()
    itinerary = _owned_itinerary(session, itinerary_id)
    result = ItineraryAgent(client=session.runtime.client).replace_stop(
        itinerary, order
    )
    if isinstance(result, NoItinerary):
        return ItineraryResultOut(
            itinerary=_itinerary_out(session, itinerary),
            reason=result.reason,
            data_unavailable=result.data_unavailable,
        )
    saved = session.itineraries.save(result)
    return ItineraryResultOut(itinerary=_itinerary_out(session, saved))


@router.put(
    "/itineraries/{itinerary_id}/status",
    response_model=ItineraryOut,
    response_model_by_alias=True,
)
def set_itinerary_status(itinerary_id: str, body: ItineraryStatusIn) -> ItineraryOut:
    """Move a plan along: proposed, confirmed, or cancelled.

    `completed` is not settable. A person cannot mark a future evening done, and
    the reflection form is what actually records that one happened.

    There is no status meaning "they said no". A plan the other person did not
    take up is `cancelled`, indistinguishable from one nobody got round to —
    invariant 2's rule, still holding after the reveal.
    """
    session = get_session()
    _owned_itinerary(session, itinerary_id)
    if body.status not in USER_SETTABLE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"status must be one of {list(USER_SETTABLE_STATUSES)}; "
                f"{body.status!r} is set by Spark, not by a person"
            ),
        )
    updated = session.itineraries.set_status(
        itinerary_id, session.viewer_user_id(), body.status
    )
    assert updated is not None      # _owned_itinerary already proved ownership
    return _itinerary_out(session, updated)


# ---------------------------------------------------------------------------
# After the date — private, and structurally so
# ---------------------------------------------------------------------------


@router.post(
    "/itineraries/{itinerary_id}/reflection",
    response_model=ReflectionOut,
    response_model_by_alias=True,
)
def write_reflection(itinerary_id: str, body: ReflectionIn) -> ReflectionOut:
    """How the date went, for the person who was on it.

    PRIVATE. It is stored against this viewer, returned only to this viewer, and
    the other person is never told it exists. Nothing in the response, and
    nothing this route triggers, is observable by them — no notification, no
    status change on their side, no silence that begins the moment it is
    submitted.

    Two things happen, and the second is deliberately small. The reflection is
    stored whole, for the person who wrote it. Separately, `planning_signal` may
    emit ONE ordinary piece of Date Studio feedback about the PLAN — the same
    kind a thumbs-down produces — so that what Spark suggests next can improve.
    Nothing about the human being is stored, ranked or learned, and
    `second_date` reaches the recommender in no form at all.
    """
    session = get_session()
    itinerary = _owned_itinerary(session, itinerary_id)
    owner_id = itinerary.owner_id

    if body.second_date not in ("yes", "maybe", "no"):
        raise HTTPException(
            status_code=422, detail="secondDate must be yes, maybe or no"
        )

    reflection = session.itineraries.record_reflection(
        itinerary_id=itinerary_id,
        lockin_id=itinerary.lockin_id,
        owner_id=owner_id,
        overall=body.overall,
        ratings=body.ratings,
        second_date=body.second_date,
        notes=body.notes,
    )

    # A date somebody reflected on is a date that happened.
    if itinerary.status != "completed":
        session.itineraries.set_status(itinerary_id, owner_id, "completed")

    signal = reflection.planning_signal()
    if signal is not None and session.date_memory.get_plan(itinerary.path_id):
        action, reasons = signal
        session.date_memory.record_feedback(
            DatePlanFeedback(
                feedback_id=f"fb-refl-{reflection.reflection_id}",
                plan_id=itinerary.path_id,
                lockin_id=itinerary.lockin_id,
                owner_id=owner_id,
                action=action,
                reasons=reasons,
                created_at=datetime.now(),
            )
        )

    return _reflection_out(reflection)


@router.get(
    "/itineraries/{itinerary_id}/reflection",
    response_model=ReflectionOut,
    response_model_by_alias=True,
)
def read_reflection(itinerary_id: str) -> ReflectionOut:
    """This viewer's own reflection. There is no route that returns anyone
    else's, and there must not be one."""
    session = get_session()
    itinerary = _owned_itinerary(session, itinerary_id)
    reflection = session.itineraries.reflection_for(itinerary_id, itinerary.owner_id)
    if reflection is None:
        raise HTTPException(
            status_code=404, detail="you have not written one for this date"
        )
    return _reflection_out(reflection)


@router.delete("/reflections/{reflection_id}")
def forget_reflection(reflection_id: str) -> dict:
    """Delete your own reflection. Soft, so the audit trail survives; invisible
    to everybody either way."""
    session = get_session()
    removed = session.itineraries.forget_reflection(
        reflection_id, session.viewer_user_id()
    )
    if not removed:
        raise HTTPException(status_code=404, detail=f"no reflection {reflection_id}")
    return {"forgotten": True}


def _reflection_out(reflection) -> ReflectionOut:
    return ReflectionOut(
        reflection_id=reflection.reflection_id,
        itinerary_id=reflection.itinerary_id,
        lock_in_id=reflection.lockin_id,
        overall=reflection.overall,
        ratings=dict(reflection.ratings),
        second_date=reflection.second_date,
        notes=reflection.notes,
        created_at=reflection.created_at.isoformat(),
    )


def _day_label(bucket: str) -> str:
    """A bucket read as a day, for the plan header.

    A LABEL, not a date. Nothing here has agreed a calendar day with anybody,
    and printing "Saturday 6 September" would imply it had.
    """
    return {
        "early_morning": "An early start",
        "morning": "A morning",
        "midday": "Lunchtime",
        "afternoon": "An afternoon",
        "evening": "An evening",
        "night": "A late one",
    }.get(bucket, "An evening")


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


@router.get("/demo/personas")
def demo_personas() -> list[dict]:
    """People an operator can be, for a demo.

    DEMO ONLY, and worth being precise about why it is not a privacy hole:
    there is no auth, so "which synthetic persona is this browser following" is
    a presenter's setting rather than a user's identity. Nothing here is
    reachable from the product's own screens, and it exposes only what the
    matcher already uses — never an identity, never a location.
    """
    return get_session().demo_personas()


@router.post("/demo/act-as")
def demo_act_as(user_id: str) -> dict:
    """Follow this persona's day. Drops the current encounter."""
    session = get_session()
    session.act_as(user_id)
    return {"actingAs": user_id}


@router.post("/demo/new-encounter")
def demo_new_encounter() -> dict:
    """Another encounter, now.

    Implemented as "let it be tomorrow", because one encounter per person per
    day IS the product and the id derives from the day. Minting a second
    encounter for a single day would be a demo control showing something the
    system does not do.

    Keeps lock-ins and Date Studio memory; `/demo/reset` clears those.
    """
    session = get_session()
    session.new_encounter_tomorrow()
    return {"day": session.clock.current.isoformat()}


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
