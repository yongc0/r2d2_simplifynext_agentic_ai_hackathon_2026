"""The live encounter, and the graph that owns it.

One `SparkSession` per process. It holds the seeded world, the supervisor graph
and the SQLite checkpointer, and it exposes the four moments the client needs:
open an encounter, answer the notification, run the call, answer the gate.

**The two consent gates are the graph's `interrupt()` calls.** `accept()` and
`consent()` below are `Command(resume=...)` and nothing else — there is no
branch in this file that decides an outcome, and no path to an identity that
does not go through `src/safety/consent.py`.

Because the checkpointer is SQLite, an encounter halted at the reveal gate
survives the server being restarted. That is not a nicety: in the real product
the two answers can be days apart, and it is the property that lets the gate be
an interrupt rather than a flag in a database.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path

from langgraph.types import Command

from src.agents.continuity import ContinuityAgent
from src.agents.delivery import EncounterDelivery
from src.agents.match import MatchAgent
from src.clock import SimClock
from src.config import SETTINGS
from src.graph.state import SparkRuntime
from src.graph.supervisor import build_encounter_graph, pending_gate, sqlite_checkpointer
from src.ids import encounter_id
from src.mcp.registry import MCPClient
from src.memory.date_memory import DateMemoryStore
from src.memory.itineraries import ItineraryStore
from src.mcp.services import WORLD
from src.safety.consent import ConsentLedger, reveal_permitted
from src.safety.trust import TrustAndSafety
from src.schemas.core import (
    Encounter,
    EncounterState,
    LockIn,
    LockInState,
    TimeBucket,
    User,
)
from src.sim.world import SimWorldBuilder
from src.telemetry.trace import mark_internal, setup_tracing

DAY_ZERO = Date(2026, 9, 1)


#: Durable session state, kept in the SAME SQLite file as the checkpoints.
#:
#: `run_id` used to live only in memory. It is mixed into every thread id, so
#: after a demo reset the checkpoints were written under `enc-...#1` — and a
#: NEW process started at run 0, looked under `enc-...#0`, and could not find
#: them. The graph's own durability was real; the key needed to address it was
#: not, which made "the consent gate survives a restart" true of the library and
#: false of the product.
#:
#: Same file as the checkpoints on purpose: the mapping and the thing it maps to
#: must be deleted together, or a stale run id points at checkpoints that are
#: gone.
_STATE_TABLE = "spark_session_state"


def _state_conn(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_STATE_TABLE} "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def read_session_state(path: Path, key: str, default: str = "") -> str:
    conn = _state_conn(path)
    try:
        row = conn.execute(
            f"SELECT value FROM {_STATE_TABLE} WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default
    finally:
        conn.close()


def write_session_state(path: Path, key: str, value: str) -> None:
    conn = _state_conn(path)
    try:
        conn.execute(
            f"INSERT INTO {_STATE_TABLE} (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


class EncounterNotFound(LookupError):
    """No such encounter, in memory or in the checkpoint. Maps to HTTP 404."""


#: Returned by `planning_refusal` when the lock-in does not exist at all.
#: The routes turn this into a 404 and every other refusal into a 409, so
#: "no such connection" and "not open for planning" stay distinguishable.
UNKNOWN_LOCKIN = "unknown"


class EncounterClosed(RuntimeError):
    """The encounter was closed for safety and may not be resumed.

    Maps to a neutral close-out, never to an error the other party could
    notice. Raised when someone has told Guardian that something felt off:
    from that point the reveal path is shut, and no later answer can reopen it.
    """


class GateNotPending(RuntimeError):
    """A resume was attempted for a gate the graph is not halted on.

    Maps to HTTP 409. This is the exception that closes the hole found in the
    code-review audit: ``Command(resume=...)`` is delivered to WHICHEVER
    interrupt is pending, so a second ``/respond`` answered the REVEAL gate
    with two yes votes nobody had cast, and the user's later explicit "no"
    arrived after the identities had already been exchanged.

    A wrong-order resume is therefore not a client mistake to be tolerated. It
    is a forged consent, and it is refused.
    """


@dataclass
class SparkSession:
    """Everything one server process needs to run encounters."""

    seed: int = SETTINGS.sim.seed
    personas: int = 60
    day_offset: int = 2

    runtime: SparkRuntime = field(init=False)
    graph: object = field(init=False)
    clock: SimClock = field(init=False)
    _conn: sqlite3.Connection | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    #: encounter id -> the live Encounter, so a second request finds the same one.
    _encounters: dict[str, Encounter] = field(default_factory=dict, init=False)
    #: What the simulated other party does at the reveal gate. `None` means
    #: "they say yes", which is the scripted happy path.
    #:
    #: This is a DEMO CONTROL (FRONTEND.md §8), and it exists so each branch can
    #: be filmed. It sets what the OTHER PERSON does — it never changes what the
    #: viewer is shown for a given pair of answers, which is the thing invariant
    #: 3 is about.
    forced_peer_answer: bool | None = field(default=None, init=False)
    #: Bumped on every reset, and mixed into the graph's thread id.
    #:
    #: Encounter ids are deterministic by design (`src/ids.py`) — one encounter
    #: per pair per day, so replaying a day cannot create a duplicate. That is
    #: right for the simulation and wrong for a demo reset: the same id would
    #: find the COMPLETED checkpoint from the previous take and hand back its
    #: final state instead of starting over. Every retake would show the last
    #: take's outcome.
    run_id: int = field(default=0, init=False)
    #: Today's encounter for THIS client, within this run.
    #:
    #: There is no auth yet (docs/PILOT.md §8.4), so the server cannot tell two
    #: browsers apart and "one encounter per person per day" has to be held
    #: here instead. Without it a second POST /api/encounters runs the starter
    #: search again, finds the first user already taken, and opens a SECOND
    #: encounter belonging to somebody else — which the client would then show
    #: as its own.
    _current_eid: str | None = field(default=None, init=False)
    #: Whose day the demo is following, when an operator has chosen (§8).
    #:
    #: `None` means "find someone whose day goes somewhere", which is the right
    #: default and a poor demo control: you get whoever the search lands on.
    #: Setting this is how a presenter shows two different people without
    #: resetting the world between them.
    preferred_starter: str | None = field(default=None, init=False)
    #: lock-in id -> the LockIn, for this run.
    #:
    #: `/api/lockins` and `/api/briefs` returned `[]` for the whole build because
    #: the only lock-in store lived in `sim/engine.py`, behind the simulation
    #: rather than behind the API. That made the continuity half of the product
    #: — the part that justifies "plans, acts and adapts over time" — filmable
    #: only on MockAdapter. This is that store, on the session, opened by the
    #: same mutual reveal the graph performs.
    _lockins: dict[str, LockIn] = field(default_factory=dict, init=False)
    #: Simulated days added by the demo controls, so a week-5 brief can be
    #: reached inside a five-minute recording.
    day_offset_extra: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        setup_tracing()
        self._build()

    # -----------------------------------------------------------------
    def _build(self) -> None:
        # Read the durable run id BEFORE anything else touches the graph. A new
        # process must address the same threads the previous one wrote, and this
        # is the only thing that makes that possible.
        db = SETTINGS.checkpoint_db
        self.run_id = int(read_session_state(db, "run_id", "0") or 0)
        self._current_eid = read_session_state(db, "current_eid", "") or None

        builder = SimWorldBuilder(seed=self.seed, persona_count=self.personas)
        builder.build(day_zero=DAY_ZERO, days=self.day_offset + 14)

        client = MCPClient()
        trust = TrustAndSafety()
        ledger = ConsentLedger()
        clock = SimClock(DAY_ZERO)
        clock.advance(self.day_offset)

        self.clock = clock
        self.ledger = ledger
        self.runtime = SparkRuntime(
            client=client,
            trust=trust,
            ledger=ledger,
            delivery=EncounterDelivery(client=client, ledger=ledger),
            match=MatchAgent(
                client=client, trust=trust, max_lockins=SETTINGS.rules.max_lockins
            ),
            continuity=ContinuityAgent(client=client),
            clock=clock,
            users=dict(WORLD.users),
            encounter_counts=Counter(),
        )

        # Date Studio's preference memory. Same file as the checkpoints, so the
        # memory and the encounters it is about are deleted together — a stale
        # preference store pointing at encounters that no longer exist is worse
        # than no store. Survives a restart; cleared only by an explicit demo
        # reset, because a preference learned in rehearsal would quietly change
        # the ranking on camera.
        self.date_memory = DateMemoryStore(SETTINGS.checkpoint_db)
        # Plans and the private reflections written after them. Same file, same
        # reasoning; separate store because reflections are one person's and the
        # read paths must not be able to forget that.
        self.itineraries = ItineraryStore(SETTINGS.checkpoint_db)

        # Durable, so the consent gate survives a restart. `runs/` is gitignored.
        saver, conn = sqlite_checkpointer(SETTINGS.checkpoint_db)
        self._conn = conn
        self.graph = build_encounter_graph(self.runtime, checkpointer=saver)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -----------------------------------------------------------------
    # The four moments
    # -----------------------------------------------------------------

    def open_encounter(self, user_id: str | None = None) -> tuple[Encounter, dict]:
        """Run the graph up to the accept gate, and halt there.

        Returns the encounter and the graph result. If nobody eligible crossed
        this user's path today the encounter is ABANDONED — a quiet day, which
        is a normal outcome and not an error.
        """
        with self._lock:
            starter = (
                user_id
                or self.preferred_starter
                or self._first_user_with_a_candidate()
            )
            day = self.clock.current
            eid = encounter_id(day.isoformat(), starter, "api")

            # ONE ENCOUNTER PER PERSON PER DAY, and re-invoking a thread that
            # is halted at a gate would discard the pending interrupt. So a
            # repeat call returns what is already open rather than opening
            # another. `POST /api/demo/reset` is how a new one is started.
            if self._current_eid is not None:
                existing = self.require_encounter(self._current_eid)
                return existing, {"encounter": existing}
            encounter = Encounter(
                id=eid,
                match_id=f"match-{day.isoformat()}-{starter}",
                day=day,
                user_a=starter,
                user_b=f"{starter}-tbd",
            )
            result = self.graph.invoke(                     # type: ignore[attr-defined]
                {
                    "encounter": encounter,
                    "users": {starter: WORLD.users[starter]},
                    "day": day,
                    "trail": [],
                },
                self._config(eid),
            )
            encounter = result["encounter"]
            self._encounters[eid] = encounter
            self._current_eid = eid
            # Durable, so a restarted process knows which encounter is today's
            # without having to guess or re-run the starter search.
            write_session_state(SETTINGS.checkpoint_db, "current_eid", eid)
            return encounter, result

    def accept(self, eid: str, viewer_yes: bool, peer_yes: bool = True) -> dict:
        """Resume the accept gate. This is `Command(resume=...)` and nothing more.

        `peer_yes` is what the simulated other party does. In the pilot it comes
        from the real second device instead; the graph does not know or care
        which, because it only ever sees two answers.
        """
        with self._lock:
            encounter = self.require_encounter(eid)
            # Refuse unless the ACCEPT gate is the pending one. Without this, a
            # repeated /respond is delivered to whatever interrupt comes next —
            # including the reveal gate, carrying two yes votes nobody cast.
            self._require_gate(eid, "accept")
            answers = {
                encounter.user_a: "yes" if viewer_yes else "no",
                encounter.user_b: "yes" if peer_yes else "no",
            }
            result = self.graph.invoke(                     # type: ignore[attr-defined]
                Command(resume=answers), self._config(eid)
            )
            self._encounters[eid] = result["encounter"]
            return result

    def consent(self, eid: str, viewer_yes: bool, peer_yes: bool | None = None) -> dict:
        """Resume the reveal gate.

        Whatever comes back, this method does not decide it. The mutual-yes
        check is `src/safety/consent.py::reveal_permitted`, and the only
        constructor of an identity-bearing view is `build_reveal`, which
        refuses without one.
        """
        with self._lock:
            encounter = self.require_encounter(eid)
            # Refused BEFORE the gate is even inspected. Nothing about a closed
            # encounter should reach the graph: not a resume, not a consent
            # record, not a vote invented on someone's behalf.
            if self.guardian_closed(eid):
                raise EncounterClosed(
                    f"encounter {eid} was closed for safety and cannot be "
                    "resumed. No identity is exchanged on a closed encounter, "
                    "whatever is answered afterwards."
                )
            # The gate this method is permitted to answer, and only this one.
            self._require_gate(eid, "reveal")
            if peer_yes is None:
                peer_yes = (
                    self.forced_peer_answer
                    if self.forced_peer_answer is not None
                    else True
                )
            answers = {
                encounter.user_a: "yes" if viewer_yes else "no",
                encounter.user_b: "yes" if peer_yes else "no",
            }
            result = self.graph.invoke(                     # type: ignore[attr-defined]
                Command(resume=answers), self._config(eid)
            )
            encounter = result["encounter"]
            self._encounters[eid] = encounter
            self._open_lockin_if_revealed(encounter, result)
            return result

    # -----------------------------------------------------------------
    def _open_lockin_if_revealed(self, encounter: Encounter, result: dict) -> None:
        """Open the lock-in, but only on a genuine mutual yes.

        Gated on `reveal_permitted` — the SAME function that guards the identity
        itself — rather than on the encounter's state or on what this method was
        called with. A lock-in carries a name, so anything that can create one
        without a mutual reveal is invariant 1 with an extra step.

        Mirrors `SimulationEngine._open_lockin`, including writing each person
        their own first note: a brief with nothing to cite is a reminder, and
        the Continuity Agent refuses to produce one.
        """
        # `reveal_allowed`, not `reveal_permitted`: a lock-in carries a name,
        # so it must clear the safety closure as well as the consent check.
        if not self.reveal_allowed(encounter):
            return

        lid = result.get("lockin_id") or f"lock-{encounter.id}"
        if lid in self._lockins:
            return

        now = encounter.call_ended or self.clock.at(19, 3)
        lockin = LockIn(
            id=lid,
            pair_id=lid,
            user_a=encounter.user_a,
            user_b=encounter.user_b,
            opened_at=now,
            last_contact=now,
            contacts=1,
        )
        self._lockins[lid] = lockin

        # A lock-in consumes a slot on both sides. The ceiling is what makes
        # ten connections remain a bounded attention pool rather than a feed.
        for uid in encounter.participants():
            user = WORLD.users[uid]
            user.lockin_slots = max(0, user.lockin_slots - 1)

        # Each person gets their OWN note, in their own memory.
        shared = sorted(
            set(WORLD.users[encounter.user_a].profile.interests)
            & set(WORLD.users[encounter.user_b].profile.interests)
        )
        topic = shared[0] if shared else "what you are both here for"
        for uid in encounter.participants():
            self.runtime.continuity.remember(lockin, uid, topic, now, source="call")

    # -----------------------------------------------------------------
    def lockins(self) -> list[LockIn]:
        """Every lock-in open in this run, newest first."""
        return sorted(
            self._lockins.values(), key=lambda l: l.opened_at, reverse=True
        )

    def viewer_id(self, lockin: LockIn) -> str:
        """Whose side we are rendering. No auth yet, so it is `user_a` — the
        person whose day the demo is following (docs/PILOT.md §8)."""
        return lockin.user_a

    def lockin(self, lockin_id: str) -> "LockIn | None":
        return self._lockins.get(lockin_id)

    def planning_refusal(self, lockin_id: str) -> str | None:
        """Why date planning is not available, or None if it is.

        ONE function, so every planning route refuses for the same reasons in
        the same order. The conditions are the ones from the product decision
        record, and they are all server-side: a React redirect is helpful, but
        it is never the boundary.

        Returns a sentence rather than a bool because the client shows it, and
        "no" without a reason is the kind of dead end people file bugs about.
        """
        lockin = self._lockins.get(lockin_id)
        if lockin is None:
            # The sentinel the routes turn into a 404. Everything else below is
            # a 409: the lock-in exists, planning is simply not open on it.
            return UNKNOWN_LOCKIN

        if lockin.state is LockInState.RELEASED:
            return "This connection has been released."

        viewer_id = self.viewer_id(lockin)
        if viewer_id not in (lockin.user_a, lockin.user_b):
            # Belt and braces: `viewer_id` derives from the lock-in itself, so
            # this cannot currently fire. It stays because the day auth lands,
            # a foreign lock-in becomes reachable and this is where it stops.
            return "This connection is not yours."

        encounter_id = lockin.id.replace("lock-", "", 1)
        if self.guardian_closed(encounter_id):
            # The safety closure outranks every retention feature. Planning an
            # evening for someone who has just said something felt off is the
            # worst thing this product could do.
            return "This connection is closed."

        for uid in (lockin.user_a, lockin.user_b):
            user = WORLD.users.get(uid)
            if user is not None and not user.consent_scope.allow_date_suggestions:
                return "One of you has turned date suggestions off."
        return None

    def demo_personas(self, limit: int = 6) -> list[dict]:
        """People an operator can choose to be, with enough to tell them apart.

        Filtered by the deterministic SHORTLIST, which is cheap and makes no
        model call. That is a strong indicator, not a guarantee: the encounter
        itself runs `select()`, which can still reject everyone, so a quiet day
        remains possible. It is a true outcome and the client shows it as one —
        this filter just stops most of the wasted clicks in a recording.

        DEMO ONLY. This is not a user list and there is no route that exposes
        one to a user — it exists because there is no auth, and switching who
        the demo is following is otherwise a server restart.
        """
        out: list[dict] = []
        day = self.clock.current
        with mark_internal():
            for user_id in sorted(WORLD.users):
                if len(out) >= limit:
                    break
                user = WORLD.users[user_id]
                pool = self.runtime.client.try_call(
                    "spark-overlap", "overlap_pool", default={"candidates": []},
                    user_id=user_id, day=day.isoformat(),
                ) or {"candidates": []}
                candidates = [
                    WORLD.users[c["candidate_id"]]
                    for c in pool["candidates"]
                    if c["candidate_id"] in WORLD.users
                ]
                if not candidates:
                    continue
                shortlisted, _ = self.runtime.match.shortlist(
                    user, candidates, day, set(), self.runtime.encounter_counts,
                )
                if not shortlisted:
                    continue
                out.append(
                    {
                        "user_id": user_id,
                        "handle": user.handle,
                        "intents": [i.value for i in user.profile.intents],
                        "interests": list(user.profile.interests)[:4],
                        "availability": [
                            b.value for b in user.profile.availability_window
                        ],
                    }
                )
        return out

    def viewer_user_id(self) -> str:
        """WHO THIS SESSION IS. One answer, used by everything.

        There is no auth, so "you" is a property of the session — and it has to
        resolve the same way everywhere or the app disagrees with itself. It
        did: the settings screen fell back to the first user in the world while
        the encounter used whichever starter the search landed on, so turning
        off calls turned them off for somebody else and the call connected
        anyway. A preference that silently applies to the wrong person is worse
        than one that does not apply at all.

        Resolution order, most specific first:
          the open encounter -> the persona an operator chose -> the search.
        """
        if self._current_eid is not None:
            encounter = self._encounters.get(self._current_eid)
            if encounter is not None:
                return encounter.user_a
        if self.preferred_starter is not None:
            return self.preferred_starter
        # Resolve once and remember, so every later read agrees with the
        # encounter that gets opened.
        self.preferred_starter = self._first_user_with_a_candidate()
        return self.preferred_starter

    def act_as(self, user_id: str) -> None:
        """Follow this person's day from now on.

        Drops the current encounter rather than reassigning it: an encounter
        belongs to the pair it was opened for, and quietly re-pointing one at a
        different person is exactly the kind of thing that would make a demo
        show something the system never did.
        """
        if user_id not in WORLD.users:
            raise EncounterNotFound(
                f"no persona {user_id!r} in this world. GET /api/demo/personas "
                "lists the ones whose day goes somewhere today."
            )
        with self._lock:
            self.preferred_starter = user_id
            self._current_eid = None
            write_session_state(SETTINGS.checkpoint_db, "current_eid", "")

    def new_encounter_tomorrow(self) -> None:
        """Make another encounter available, without wiping the run.

        ONE ENCOUNTER PER PERSON PER DAY is the product, and the encounter id is
        derived from the day — so "give me another" is the same thing as "let it
        be tomorrow". Advancing the clock is therefore the honest implementation
        rather than a special case that mints a second encounter for one day.

        Keeps lock-ins and Date Studio memory. Use `/demo/reset` to clear those.
        """
        self.advance_days(1)
        with self._lock:
            self._current_eid = None
            write_session_state(SETTINGS.checkpoint_db, "current_eid", "")

    def advance_days(self, days: int) -> int:
        """Move the simulated clock forward, for §8's demo controls.

        Six weeks of continuity has to fit inside five minutes, and the
        difference between a week-one brief and a week-five one is the whole
        "adapts over time" claim. Returns the new total offset.
        """
        with self._lock:
            self.day_offset_extra += days
            self.clock.advance(days)
            # A lock-in with no recent contact goes quiet. Same threshold the
            # simulation uses, so the demo and the evaluation agree.
            quiet_after = SETTINGS.rules.lockin_quiet_days
            now = self.clock.at(9, 0)
            for lockin in self._lockins.values():
                if lockin.state is LockInState.RELEASED:
                    continue
                gap = (now - lockin.last_contact).days
                lockin.state = (
                    LockInState.QUIET if gap >= quiet_after else LockInState.ACTIVE
                )
            return self.day_offset_extra

    # -----------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------

    def get(self, eid: str) -> Encounter | None:
        return self._encounters.get(eid)

    def current_encounter_id(self) -> str | None:
        """Today's encounter for this client, surviving a restart.

        There is no auth (docs/PILOT.md §8), so "whose encounter" is a property
        of the session rather than of a user. Persisting it is what lets a
        restarted process answer `POST /api/encounters` with the encounter that
        is genuinely still open, instead of running the starter search again and
        opening somebody else's.
        """
        return self._current_eid

    def user(self, user_id: str) -> User:
        return WORLD.users[user_id]

    def shared_bucket(self, a: str, b: str) -> TimeBucket | None:
        result = self.runtime.client.try_call(
            "spark-calendar", "shared_availability",
            default={"shared_buckets": []}, user_a=a, user_b=b,
        ) or {"shared_buckets": []}
        buckets = result["shared_buckets"]
        return TimeBucket(buckets[0]) if buckets else None

    def window_closes_at(self) -> datetime:
        return self.clock.at(18, 0) + timedelta(
            minutes=SETTINGS.rules.accept_window_minutes
        )

    def pending(self, result: dict) -> str | None:
        gate = pending_gate(result)
        return gate.gate if gate else None

    def reset(self, seed: int | None = None) -> None:
        """Deterministic reset, for §8's demo controls.

        The run id is incremented DURABLY and then read back by `_build`, so a
        process started after a reset lands on the same threads this one is
        about to write. Incrementing it in memory was the bug: the checkpoints
        went to run 1 and the next process looked in run 0.
        """
        with self._lock:
            self.close()
            self._encounters.clear()
            self._lockins.clear()
            # Recorded takes must be deterministic.
            DateMemoryStore(SETTINGS.checkpoint_db).clear()
            ItineraryStore(SETTINGS.checkpoint_db).clear()
            self.day_offset_extra = 0
            self.preferred_starter = None
            self.forced_peer_answer = None

            db = SETTINGS.checkpoint_db
            next_run = int(read_session_state(db, "run_id", "0") or 0) + 1
            write_session_state(db, "run_id", str(next_run))
            write_session_state(db, "current_eid", "")

            if seed is not None:
                self.seed = seed
            self._build()

    # -----------------------------------------------------------------
    def _config(self, eid: str) -> dict:
        # The run id makes each take its own thread. Deterministic within a
        # run, fresh across resets.
        return {"configurable": {"thread_id": f"{eid}#{self.run_id}"}}

    def _snapshot(self, eid: str):
        """The graph checkpoint for this encounter, or None if there is none."""
        try:
            return self.graph.get_state(self._config(eid))   # type: ignore[attr-defined]
        except Exception:
            # A thread that was never started has no checkpoint. That is a
            # missing encounter, not a server fault.
            return None

    def checkpoint_gate(self, eid: str) -> str | None:
        """WHICH interrupt the graph is halted on: "accept", "reveal", or None.

        Read from the checkpoint rather than inferred from ``Encounter.state``,
        and the difference is the whole point. ``state`` is a field the nodes
        write; the interrupt is the thing a resume is actually delivered to. If
        the two ever disagree, the interrupt is what happens — so the interrupt
        is what we check.
        """
        snapshot = self._snapshot(eid)
        if snapshot is None:
            return None
        # Prefer the per-task interrupts: they are present across LangGraph
        # versions, where ``snapshot.interrupts`` is newer.
        tasks = getattr(snapshot, "tasks", ()) or ()
        pending = [
            item
            for task in tasks
            for item in (getattr(task, "interrupts", ()) or ())
        ]
        if not pending:
            pending = list(getattr(snapshot, "interrupts", ()) or ())
        for item in pending:
            value = getattr(item, "value", None)
            if isinstance(value, dict) and value.get("gate"):
                return str(value["gate"])
        return None

    # -----------------------------------------------------------------
    # Guardian closure
    # -----------------------------------------------------------------

    def _closure_key(self, eid: str) -> str:
        """Scoped by run, like the graph threads.

        A demo reset starts a new take and increments `run_id`, so a closure
        from a previous take does not silently shut an encounter in the next
        one — the same reasoning that stops a stale checkpoint being replayed.
        """
        return f"guardian_closed:{eid}#{self.run_id}"

    def close_for_guardian(self, eid: str) -> None:
        """Shut the reveal path for this encounter, durably and idempotently.

        WRITTEN BEFORE ANYONE IS TOLD ANYTHING. The Guardian endpoint used to
        say "we have closed the encounter" while the server had done nothing at
        all — the reveal gate stayed pending, and a later `consent yes` returned
        the other person's name. The message was a claim the server could not
        back, which for a safety feature is the worst kind of bug: it is
        indistinguishable from working.

        Deliberately does NOT resume the graph. Resuming would mean supplying an
        answer for the other party that they never gave, and a fabricated
        consent record is not a safer thing than an open gate. The gate simply
        stays unanswered, and the closure below is what stops it mattering.

        Idempotent: writing twice is the same as writing once, so a repeated
        submission cannot weaken the closure.
        """
        with self._lock:
            write_session_state(SETTINGS.checkpoint_db, self._closure_key(eid), "1")

    def guardian_closed(self, eid: str) -> bool:
        """Whether this encounter was shut for safety. Read from the database,
        so it survives the process that wrote it."""
        return read_session_state(SETTINGS.checkpoint_db, self._closure_key(eid)) == "1"

    def reveal_allowed(self, encounter: Encounter) -> bool:
        """THE boundary every identity-bearing path consults.

        One function rather than a check repeated at each call site, because the
        failure this replaces was precisely a path that did not repeat it. It
        combines the two conditions that must both hold:

          - `reveal_permitted` — the call happened and both said yes, and
          - the encounter was not closed for safety.

        `POST /consent`, the lock-in store and `GET /dates` all go through here.
        """
        if self.guardian_closed(encounter.id):
            return False
        return reveal_permitted(self.ledger, encounter)

    # -----------------------------------------------------------------
    def _require_gate(self, eid: str, expected: str) -> None:
        """Refuse to resume anything but the gate that is actually pending.

        The single place ordering is enforced. Both ``accept()`` and
        ``consent()`` go through it, so neither can be reached out of turn,
        twice, or after the encounter has finished.
        """
        actual = self.checkpoint_gate(eid)
        if actual == expected:
            return

        if actual is None:
            raise GateNotPending(
                f"encounter {eid} is not waiting for an answer: it has already "
                "been answered, or it has finished. Answering a gate twice "
                "would let a repeated request stand in for the other party. "
                "Open a new encounter with POST /api/encounters."
            )
        raise GateNotPending(
            f"encounter {eid} is waiting at the {actual!r} gate, not "
            f"{expected!r}. Answer {actual!r} first — 'accept' is POST "
            "/respond, 'reveal' is POST /consent. Resuming out of order would "
            "deliver this answer to a question it was not given for."
        )

    def require_encounter(self, eid: str) -> Encounter:
        """The encounter, from memory or rebuilt from the durable checkpoint.

        The in-memory index does not survive a restart, but the SQLite
        checkpoint does — and the encounter is inside it. Reading it back is
        what makes the documented restart-recovery property true at the API
        layer, and not only in ``tests/test_graph.py``.
        """
        encounter = self._encounters.get(eid)
        if encounter is not None:
            return encounter

        snapshot = self._snapshot(eid)
        values = getattr(snapshot, "values", None) if snapshot else None
        recovered = values.get("encounter") if isinstance(values, dict) else None
        if isinstance(recovered, Encounter):
            self._encounters[eid] = recovered
            return recovered

        raise EncounterNotFound(
            f"no encounter {eid!r}. It was never opened in this session, or it "
            "belonged to an earlier take — POST /api/demo/reset starts a new "
            "run and previous encounter ids are deliberately not resumable. "
            "Open one with POST /api/encounters."
        )

    def _first_user_with_a_candidate(self) -> str:
        """A user whose day actually goes somewhere.

        Most people's overlap pool does not survive the intent, language,
        availability and cooldown rules on any given day — a quiet day is a
        normal day. That is a poor default for a demo, so this looks for one
        that does not end immediately.
        """
        day = self.clock.current
        fallback: str | None = None
        best_overlap = -1
        # The probes below are the DEMO choosing whose day to follow, not an
        # agent making a decision. Each one emitted a pair of tool spans, so the
        # Director panel opened with twenty near-identical rows before anything
        # worth watching happened — the first thing a judge sees, and the least
        # interesting part of the run. Marked internal so the feed drops them;
        # they are still in the trace file for anyone debugging the search.
        with mark_internal():
            for user_id in sorted(WORLD.users):
                pool = self.runtime.client.try_call(
                    "spark-overlap", "overlap_pool", default={"candidates": []},
                    user_id=user_id, day=day.isoformat(),
                ) or {"candidates": []}
                candidates = [
                    WORLD.users[c["candidate_id"]]
                    for c in pool["candidates"]
                    if c["candidate_id"] in WORLD.users
                ]
                if not candidates:
                    continue
                # `shortlist()`, not `select()`. We only need to know WHETHER anyone
                # is eligible, and shortlist answers that from the deterministic
                # rules alone. `select()` would make a model call per user searched
                # — on Groq that is ~4.5s each, so opening an encounter took tens of
                # seconds and varied run to run. The model is for choosing between
                # eligible people, not for discovering that some exist.
                shortlisted, _rejected = self.runtime.match.shortlist(
                    WORLD.users[user_id], candidates, day, set(),
                    self.runtime.encounter_counts,
                )
                if not shortlisted:
                    continue

                # DEMO STAGING, and labelled as such.
                #
                # Prefer a starter whose shortlist contains someone they actually
                # have something in common with, so the Date Agent has material to
                # work with on camera. A third of pairs in this world share no
                # interests at all, which is a true fact about the world and a poor
                # opening shot.
                #
                # This affects ONLY the demo's choice of whose day to follow. It
                # does not touch the Match Agent's ranking, the eligibility rules,
                # or the evaluation — `eval/run_arms.py` never calls this. Staging a
                # demo is legitimate; tuning the thing being measured is not.
                starter_user = WORLD.users[user_id]
                overlap = max(
                    (
                        len(set(starter_user.profile.interests) & set(c.profile.interests))
                        for c in shortlisted_users(shortlisted, candidates)
                    ),
                    default=0,
                )
                if overlap >= 2:
                    # Enough for the Date Agent to build more than one evening on.
                    return user_id
                if overlap > best_overlap:
                    best_overlap, fallback = overlap, user_id
                elif fallback is None:
                    fallback = user_id
        if fallback is not None:
            # Somebody has an encounter, just not one with common ground. That
            # is a normal day and the Date Agent will say so honestly.
            return fallback
        raise RuntimeError(
            "Nobody has an eligible candidate today — every overlap failed the "
            "intent, language, availability or cooldown rules. Try a different "
            "SPARK_SIM_SEED, or more personas."
        )


def shortlisted_users(shortlisted, candidates):
    """The `User` objects behind a shortlist, whatever shape its entries take.

    `shortlist()` returns scored candidates; this pulls the users back out so
    the demo staging above can look at their interests without depending on the
    scoring type's field names.
    """
    by_id = {c.id: c for c in candidates}
    out = []
    for entry in shortlisted:
        cid = getattr(entry, "candidate_id", None) or getattr(entry, "id", None)
        if cid in by_id:
            out.append(by_id[cid])
    return out


#: One session per process, built lazily so importing the app is cheap.
_session: SparkSession | None = None
_session_lock = threading.Lock()


def get_session() -> SparkSession:
    global _session
    with _session_lock:
        if _session is None:
            _session = SparkSession()
        return _session


def reset_session(seed: int | None = None) -> SparkSession:
    session = get_session()
    session.reset(seed)
    return session


def terminal_state(encounter: Encounter) -> bool:
    return encounter.state in (
        EncounterState.ABANDONED,
        EncounterState.CLOSED,
        EncounterState.RELEASED,
    )
