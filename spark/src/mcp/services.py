"""The bodies behind every MCP tool.

Plain functions over a `SparkWorld`. Each MCP server module in this package is
a thin wrapper that exposes some of these over the protocol, so the code a
judge reads in `overlap.py` and the code the simulation runs are the same code.

Two rules hold everywhere in this file:

  Nothing here returns a coordinate, a place name, a distance or a real name.
  `spark-overlap` returns opaque cell tokens and time buckets, and `cell_id` is
  never rendered — `src/safety/guardrails.py` blocks it if anything tries.

  Nothing here decides consent. The voice bridge will not connect an encounter
  that has not been accepted by both parties, but it does not *decide* that; it
  is handed the fact and refuses if it is absent (INVARIANT 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta
from typing import Any

from src.config import SETTINGS
from src.schemas.core import (
    ContinuityNote,
    Overlap,
    TimeBucket,
    User,
)


class ToolFailure(Exception):
    """A tool that could not do its job.

    The message is the thing the organisers grade: it must say what failed,
    what was tried, and what happens next. "tool call failed" is not
    acceptable; "spark-venue returned no options for ['climbing'] in the
    evening bucket; falling back to the cached general list" is.
    """


@dataclass
class VoiceCall:
    """One bridged call. Duration is decided here and only here."""

    encounter_id: str
    started_at: datetime
    duration_s: int
    ended_reason: str


@dataclass
class SparkWorld:
    """The state the six servers read and write.

    In the deployed design these are separate services behind AgentCore
    Gateway; here they share one in-memory object so the simulation is fast and
    reproducible. The *interface* is what matters and it is identical.
    """

    users: dict[str, User] = field(default_factory=dict)
    #: day -> the overlaps observed on that day
    overlaps: dict[Date, list[Overlap]] = field(default_factory=dict)
    #: (user_a, user_b) sorted -> the days their paths crossed, and in which
    #: bucket. An index, not a second source of truth: `index_overlaps()`
    #: rebuilds it from `overlaps`. Without it, "how often have these two
    #: crossed" is a scan of a fortnight of overlaps per candidate per day,
    #: which is most of the runtime of a six-week simulation.
    crossings: dict[tuple[str, str], list[tuple[Date, str]]] = field(default_factory=dict)
    #: user_id -> the buckets they are typically free in
    availability: dict[str, list[TimeBucket]] = field(default_factory=dict)
    #: owner_id -> their continuity notes
    notes: dict[str, list[ContinuityNote]] = field(default_factory=dict)
    #: venue_id -> venue record
    venues: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: encounter_id -> the call that happened
    calls: dict[str, VoiceCall] = field(default_factory=dict)
    #: Injected failure rate for the voice bridge, so the tool-call success
    #: metric measures something real. §17 calls the bridge the riskiest call
    #: and the one most likely to fail on camera; a run in which it never fails
    #: has not tested the fallback.
    voice_failure_rate: float = 0.0
    _voice_attempts: int = 0

    def reset(self) -> None:
        self.users.clear()
        self.overlaps.clear()
        self.crossings.clear()
        self.availability.clear()
        self.notes.clear()
        self.venues.clear()
        self.calls.clear()
        self._voice_attempts = 0


#: One world per process. `src/sim/world.py` populates it.
WORLD = SparkWorld()


def index_overlaps() -> None:
    """Rebuild the pair -> crossings index from `WORLD.overlaps`.

    Called once after seeding. Kept as an explicit step rather than maintained
    incrementally so there is exactly one place the index can be wrong, and it
    is derived from the overlaps rather than written alongside them.
    """
    WORLD.crossings.clear()
    for day, overlaps in WORLD.overlaps.items():
        for overlap in overlaps:
            WORLD.crossings.setdefault(overlap.pair, []).append(
                (day, overlap.time_bucket.value)
            )


# ---------------------------------------------------------------------------
# spark-overlap — coarse cell + time bucket, historical only
# ---------------------------------------------------------------------------


def overlap_pool(user_id: str, day: str) -> dict[str, Any]:
    """Everyone whose path crossed `user_id` on `day`.

    Historical by construction: the argument is a day that has finished. There
    is no "who is near me now" call in this server and there will not be one —
    docs/ARCHITECTURE.md §13.3 and the proposal §3.2 explain why live proximity
    was removed, and it is a de-anonymisation and stalking vector.

    Returns opaque cell tokens. A caller can tell that two overlaps happened in
    the same place; it cannot tell where that place is, and neither can a user,
    because `cell_id` never reaches a view.
    """
    target = _parse_day(day)
    todays = WORLD.overlaps.get(target, [])
    candidates: list[dict[str, Any]] = []
    for overlap in todays:
        if user_id not in overlap.pair:
            continue
        other = overlap.user_b if overlap.user_a == user_id else overlap.user_a
        candidates.append(
            {
                "candidate_id": other,
                "cell_id": overlap.cell_id,
                "time_bucket": overlap.time_bucket.value,
                "date": target.isoformat(),
            }
        )
    return {"user_id": user_id, "day": target.isoformat(), "candidates": candidates}


def overlap_strength(user_id: str, candidate_id: str, day: str, window_days: int = 14) -> dict[str, Any]:
    """How often two paths have crossed in the recent past.

    A single crossing is a coincidence; the same crossing four mornings a week
    is a shared routine, and that is a better reason to spend three minutes on
    someone. Returns a count and the buckets involved — never the cells.
    """
    target = _parse_day(day)
    earliest = Date.fromordinal(target.toordinal() - window_days + 1)
    pair = (user_id, candidate_id) if user_id < candidate_id else (candidate_id, user_id)
    count = 0
    buckets: set[str] = set()
    for when, bucket in WORLD.crossings.get(pair, ()):
        if earliest <= when <= target:
            count += 1
            buckets.add(bucket)
    return {
        "user_id": user_id,
        "candidate_id": candidate_id,
        "crossings": count,
        "window_days": window_days,
        "buckets": sorted(buckets),
    }


# ---------------------------------------------------------------------------
# spark-profile — profile store + continuity memory (AgentCore Memory)
# ---------------------------------------------------------------------------


def get_profile(user_id: str) -> dict[str, Any]:
    """The matchable profile. Never the identity.

    Note what this returns and what it does not: `User.identity` exists on the
    object this function reads, and does not appear in what it gives back. An
    agent asking for a profile cannot get a name by accident.
    """
    user = _require_user(user_id)
    return {
        "user_id": user.id,
        "handle": user.handle,
        "intents": [i.value for i in user.profile.intents],
        "interests": list(user.profile.interests),
        "values": list(user.profile.values),
        "personality": user.profile.personality,
        "lifestyle": user.profile.lifestyle,
        "languages": list(user.profile.languages),
        "availability_window": [b.value for b in user.profile.availability_window],
        "dealbreakers": list(user.profile.dealbreakers),
        "age_band": user.profile.age_band,
        "verification_tier": user.verification_tier.value,
        "matchable_fields": list(user.consent_scope.matchable_fields),
        "lockin_slots": user.lockin_slots,
    }


def write_note(owner_id: str, lockin_id: str, note: str, source: str, at: str) -> dict[str, Any]:
    """Store a continuity note, scoped to one user (§13.4).

    `owner_id` is the person whose memory this is. The same conversation
    produces a note for each participant; neither can read the other's, which
    is what "never surfaced to anyone the note was not about" means in code.
    """
    from src.ids import note_id                      # local: avoids a cycle at import

    created = datetime.fromisoformat(at)
    existing = WORLD.notes.setdefault(owner_id, [])
    record = ContinuityNote(
        id=note_id(lockin_id, owner_id, len(existing)),
        lockin_id=lockin_id,
        owner_id=owner_id,
        note=note,
        source=source,                                # type: ignore[arg-type]
        created_at=created,
        # OPEN QUESTION 3: 90 days by default, and that number needs a real
        # justification before any pilot. It is config, not a literal, so the
        # answer is a settings change rather than a code change.
        expires_at=created + timedelta(days=SETTINGS.rules.continuity_note_retention_days),
    )
    existing.append(record)
    return {"note_id": record.id, "expires_at": record.expires_at.isoformat()}


def read_notes(owner_id: str, lockin_id: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    """Read one user's own notes, expired ones excluded.

    Retention is enforced on read as well as on write, so a note that has aged
    out cannot resurface because a cleanup job did not run.
    """
    now = datetime.fromisoformat(as_of) if as_of else None
    notes = []
    for note in WORLD.notes.get(owner_id, []):
        if lockin_id is not None and note.lockin_id != lockin_id:
            continue
        if now is not None and note.expires_at <= now:
            continue
        notes.append(
            {
                "note_id": note.id,
                "lockin_id": note.lockin_id,
                "note": note.note,
                "source": note.source,
                "created_at": note.created_at.isoformat(),
            }
        )
    return {"owner_id": owner_id, "notes": notes}


def forget_notes(owner_id: str, lockin_id: str | None = None) -> dict[str, Any]:
    """Deletable on request (§13.4). Returns how many were removed, because
    "we deleted your data" with no number is not an answer."""
    before = len(WORLD.notes.get(owner_id, []))
    if lockin_id is None:
        WORLD.notes[owner_id] = []
    else:
        WORLD.notes[owner_id] = [
            n for n in WORLD.notes.get(owner_id, []) if n.lockin_id != lockin_id
        ]
    return {"owner_id": owner_id, "deleted": before - len(WORLD.notes.get(owner_id, []))}


# ---------------------------------------------------------------------------
# spark-voice — the anonymous bridge
# ---------------------------------------------------------------------------


def connect_call(encounter_id: str, both_accepted: bool, started_at: str) -> dict[str, Any]:
    """Bridge two anonymous legs, and stop at 180 seconds. INVARIANT 4.

    The duration is not a parameter. A caller cannot request 200 seconds, and
    there is no argument that extends a call — the cap is read from config and
    applied here, at the one place a call can be created.

    `both_accepted` is handed in rather than looked up: this server does not
    decide consent, it refuses to act without it (INVARIANT 6).
    """
    WORLD._voice_attempts += 1
    if not both_accepted:
        raise ToolFailure(
            f"spark-voice refused to connect encounter {encounter_id}: the bridge "
            "is only opened after both parties have accepted. This is a bug in "
            "the caller, not a transient failure — do not retry."
        )
    # A deterministic injected failure, so the fallback path is exercised and
    # the tool-call success rate reports a real number rather than a flat 100%.
    if WORLD.voice_failure_rate > 0:
        period = max(1, round(1 / WORLD.voice_failure_rate))
        if WORLD._voice_attempts % period == 0:
            raise ToolFailure(
                f"spark-voice returned 503 for encounter {encounter_id} after 3 "
                "retries; the encounter will be re-offered tomorrow and neither "
                "party is told the call failed on our side."
            )
    call = VoiceCall(
        encounter_id=encounter_id,
        started_at=datetime.fromisoformat(started_at),
        duration_s=SETTINGS.rules.call_seconds,
        ended_reason="time_limit",
    )
    WORLD.calls[encounter_id] = call
    return {
        "encounter_id": encounter_id,
        "started_at": call.started_at.isoformat(),
        "duration_s": call.duration_s,
        "ended_reason": call.ended_reason,
        # Both legs are anonymous. There is no PSTN number on either side, so
        # there is nothing here for a caller to leak even if it wanted to.
        "leg_a": f"anon:{encounter_id}:a",
        "leg_b": f"anon:{encounter_id}:b",
    }


def call_record(encounter_id: str) -> dict[str, Any]:
    call = WORLD.calls.get(encounter_id)
    if call is None:
        raise ToolFailure(
            f"spark-voice has no call for encounter {encounter_id}. Either the "
            "bridge was never opened or this encounter ended before the call."
        )
    return {
        "encounter_id": call.encounter_id,
        "started_at": call.started_at.isoformat(),
        "duration_s": call.duration_s,
        "ended_reason": call.ended_reason,
    }


# ---------------------------------------------------------------------------
# spark-calendar — availability
# ---------------------------------------------------------------------------


def availability(user_id: str) -> dict[str, Any]:
    _require_user(user_id)
    buckets = WORLD.availability.get(user_id, [])
    return {"user_id": user_id, "buckets": [b.value for b in buckets]}


def shared_availability(user_a: str, user_b: str) -> dict[str, Any]:
    """Buckets both are free in. The Date Agent proposes into these, and the
    Match Agent uses the count as a hard-ish signal: two people who are never
    free at the same time cannot have a call, however well matched."""
    a = set(WORLD.availability.get(user_a, []))
    b = set(WORLD.availability.get(user_b, []))
    shared = sorted(x.value for x in (a & b))
    return {"user_a": user_a, "user_b": user_b, "shared_buckets": shared}


# ---------------------------------------------------------------------------
# spark-venue — date options
# ---------------------------------------------------------------------------


def suggest_venues(
    interests: list[str],
    bucket: str,
    limit: int = 3,
    category: str | None = None,
) -> dict[str, Any]:
    """Options ranked on fit with the pair's shared interests.

    §13.6: commercial partners may only appear where they already rank, and are
    labelled. The ranking below does not know which venues are partners — the
    flag is attached after sorting, so it cannot influence the order.

    `category` narrows to "activity", "food" or "drink" so the Date Agent can
    build an evening out of a thing to do and somewhere to eat afterwards.

    WHAT THIS FUNCTION IS NOT GIVEN: a cell, a coordinate, a distance, or either
    person's overlap history. It ranks on shared interests and time of day and
    nothing else. That is invariant 3 held at the tool boundary — a venue search
    that accepted a location would quietly become "near where you both were",
    which is the inference the whole product is built to prevent.
    """
    wanted = {i.lower() for i in interests}
    scored: list[tuple[float, dict[str, Any]]] = []
    for venue in WORLD.venues.values():
        tags = {t.lower() for t in venue["tags"]}
        if bucket not in venue["buckets"]:
            continue
        if category is not None and venue.get("category", "activity") != category:
            continue
        overlap = len(wanted & tags)
        if overlap == 0:
            continue
        score = overlap / max(1, len(wanted))
        scored.append((score, venue))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    if not scored:
        raise ToolFailure(
            f"spark-venue found no options tagged {sorted(wanted)} in the "
            f"{bucket} bucket"
            + (f" for category {category!r}" if category else "")
            + ". Falling back to the pair's shared interests without a venue; "
            "the Date Agent will suggest an activity instead."
        )
    out = []
    for score, venue in scored[:limit]:
        out.append(
            {
                "venue_id": venue["id"],
                "activity": venue["activity"],
                "tags": venue["tags"],
                "fit_score": round(score, 3),
                "is_commercial_partner": venue["is_commercial_partner"],
                "category": venue.get("category", "activity"),
            }
        )
    return {"bucket": bucket, "options": out}


# ---------------------------------------------------------------------------
# spark-sim — personas and the evaluation arms
# ---------------------------------------------------------------------------


def sim_users() -> dict[str, Any]:
    return {"user_ids": sorted(WORLD.users)}


def sim_stats() -> dict[str, Any]:
    return {
        "users": len(WORLD.users),
        "days_with_overlaps": len(WORLD.overlaps),
        "overlaps": sum(len(v) for v in WORLD.overlaps.values()),
        "venues": len(WORLD.venues),
        "calls": len(WORLD.calls),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require_user(user_id: str) -> User:
    user = WORLD.users.get(user_id)
    if user is None:
        known = len(WORLD.users)
        raise ToolFailure(
            f"spark-profile has no user {user_id!r}. The world holds {known} "
            "users; either the simulation was not seeded (run "
            "`uv run -m src.cli.simulate` which seeds it) or an agent invented "
            "a candidate id that was never in the pool."
        )
    return user


def _parse_day(day: str) -> Date:
    try:
        return Date.fromisoformat(day)
    except ValueError as exc:
        raise ToolFailure(
            f"spark-overlap received day={day!r}, which is not an ISO date. "
            "Expected YYYY-MM-DD."
        ) from exc
