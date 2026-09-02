"""The simulation engine — days, then weeks.

One class drives everything: `uv run -m src.cli.simulate` and each arm of
`uv run -m eval.run_arms` are the same code with a different match policy. That
is deliberate. If the demo ran a different path from the evaluation, the
evaluation would not be evidence about the demo.

A day:

  1. Every user without an encounter yet today gets one selected, notified and
     run through the supervisor graph.
  2. The simulated humans answer the accept gate. The graph resumes.
  3. Those who spoke answer the reveal gate, privately. The graph resumes.
  4. A mutual yes opens a lock-in and writes each person a note.

A week, on top of that:

  5. The Continuity Agent looks at every active lock-in: brief, re-entry,
     proposal, pace adjustment, or a graceful release.

Reproducible from one integer. Every random draw comes from a seeded
`random.Random`, and no wall-clock time is read anywhere.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta

from langgraph.types import Command

from src.agents.communication import CommunicationAgent
from src.agents.continuity import ContinuityAgent
from src.agents.date import DateAgent
from src.agents.delivery import EncounterDelivery
from src.agents.match import MatchAgent, MatchPolicy, RandomArm, SimilarityArm
from src.clock import SimClock
from src.config import SETTINGS
from src.graph.state import SparkRuntime
from src.graph.supervisor import build_encounter_graph
from src.ids import encounter_id, lockin_id as make_lockin_id, match_id
from src.mcp.registry import MCPClient
from src.mcp.services import WORLD
from src.safety.consent import ConsentLedger
from src.safety.trust import TrustAndSafety
from src.schemas.core import Encounter, EncounterState, LockIn, LockInState
from src.sim.personas import Persona
from src.sim.responder import Responder
from src.sim.world import SimWorldBuilder
from src.telemetry.metrics import METRICS
from src.telemetry.trace import TRACES, span


@dataclass
class ArmTotals:
    """What the three-arm comparison is made of (§19).

    Counters only. Every rate in the report is derived from these at print
    time, so no rounding or intermediate average is baked in here.
    """

    encounters_offered: int = 0
    encounters_accepted: int = 0        # both parties accepted the call
    calls_completed: int = 0
    mutual_connects: int = 0
    lockins_opened: int = 0
    met_in_person_by_day_14: int = 0
    lockins_active_at_week_4: int = 0
    lockins_released: int = 0
    days_without_candidate: int = 0
    bridge_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class SimulationResult:
    arm: str
    provider: str
    seed: int
    weeks: int
    personas: int
    totals: ArmTotals
    metrics: dict
    #: One full encounter trace, kept for the demo. The rest are discarded as
    #: the run goes on, or a six-week run would hold a million spans.
    demo_trace: str = ""
    #: A week-1 and a week-5 continuity action for the same lock-in, so the
    #: "adapts over time" claim can be looked at rather than believed.
    continuity_examples: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def rate(self, numerator: str, denominator: str) -> float | None:
        num = getattr(self.totals, numerator)
        den = getattr(self.totals, denominator)
        return None if den == 0 else num / den


@dataclass
class SimulationEngine:
    """One arm, one seed, N weeks."""

    arm: str = "spark"
    seed: int = 42
    personas: int = 200
    weeks: int = 6
    day_zero: Date = Date(2026, 9, 1)
    #: Print a line per day. Off in the evaluation, on in the CLI.
    verbose: bool = False

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed + 7919)     # a different stream to the world
        self.responder = Responder(rng=self.rng)
        self.totals = ArmTotals()
        self.lockins: dict[str, LockIn] = {}
        self.people: dict[str, Persona] = {}
        self.notes: list[str] = []
        self.continuity_examples: list[str] = []
        self.demo_trace = ""
        self._week_one_example = ""

    # -----------------------------------------------------------------
    def run(self) -> SimulationResult:
        days = self.weeks * 7
        builder = SimWorldBuilder(seed=self.seed, persona_count=self.personas)
        self.people = builder.build(day_zero=self.day_zero, days=days)

        client = MCPClient()
        trust = TrustAndSafety()
        ledger = ConsentLedger()
        clock = SimClock(self.day_zero)
        runtime = SparkRuntime(
            client=client,
            trust=trust,
            ledger=ledger,
            delivery=EncounterDelivery(client=client, ledger=ledger),
            match=self._policy(client, trust),
            continuity=ContinuityAgent(client=client),
            clock=clock,
            users=dict(WORLD.users),
            encounter_counts=Counter(),
        )
        self.runtime = runtime
        self.communication = CommunicationAgent(client=client)
        self.date_agent = DateAgent(client=client)
        self.graph = build_encounter_graph(runtime)

        with span("simulation", arm=self.arm, weeks=self.weeks, personas=self.personas):
            for _day_index in range(days):
                self._run_day(clock)
                self._run_continuity(clock)
                clock.advance()

        self._finalise(clock)
        return SimulationResult(
            arm=self.arm,
            provider=SETTINGS.model.provider,
            seed=self.seed,
            weeks=self.weeks,
            personas=self.personas,
            totals=self.totals,
            metrics=METRICS.snapshot(),
            demo_trace=self.demo_trace,
            continuity_examples=self.continuity_examples,
            notes=self.notes,
        )

    def _policy(self, client: MCPClient, trust: TrustAndSafety) -> MatchPolicy:
        """The one line that differs between the three arms."""
        if self.arm == "spark":
            return MatchAgent(client=client, trust=trust, max_lockins=SETTINGS.rules.max_lockins)
        if self.arm == "random":
            return RandomArm(
                client=client, trust=trust, rng=random.Random(self.seed + 104729),
                max_lockins=SETTINGS.rules.max_lockins,
            )
        if self.arm == "similarity":
            return SimilarityArm(
                client=client, trust=trust, max_lockins=SETTINGS.rules.max_lockins
            )
        raise ValueError(
            f"unknown arm {self.arm!r}. Use one of: spark, random, similarity."
        )

    # -----------------------------------------------------------------
    # A day
    # -----------------------------------------------------------------

    def _run_day(self, clock: SimClock) -> None:
        engaged = self.runtime.unavailable_today
        engaged.clear()
        order = sorted(WORLD.users)
        self.rng.shuffle(order)                        # fairness: no fixed advantage

        for user_id in order:
            if user_id in engaged:
                continue                               # one encounter per user per day
            # Mark the user unavailable BEFORE selecting, so the Match Agent
            # cannot pick them for themselves and cannot pick anyone who has
            # already been taken today.
            engaged.add(user_id)
            encounter = self._run_encounter(clock, user_id)
            if encounter is not None and encounter.user_b in WORLD.users:
                engaged.add(encounter.user_b)
            else:
                # No encounter happened, so this person is free to be somebody
                # else's match later in the day. Leaving them marked would make
                # a quiet day contagious.
                engaged.discard(user_id)

        if self.verbose:
            print(
                f"  day {clock.day_index + 1:>2} (week {clock.week_index}): "
                f"{self.totals.encounters_offered} offered, "
                f"{self.totals.mutual_connects} connections, "
                f"{len([l for l in self.lockins.values() if l.state is LockInState.ACTIVE])} "
                "active lock-ins"
            )

    def _run_encounter(self, clock: SimClock, user_id: str) -> Encounter | None:
        day = clock.current
        eid = encounter_id(day.isoformat(), user_id, "pending")
        encounter = Encounter(
            id=eid,
            match_id=match_id(day.isoformat(), user_id),
            day=day,
            user_a=user_id,
            user_b=f"{user_id}-tbd",                   # replaced by the select node
        )
        config = {"configurable": {"thread_id": eid}}
        state = {
            "encounter": encounter,
            "users": {user_id: WORLD.users[user_id]},
            "day": day,
            "trail": [],
        }
        # ONE span around the whole encounter (§11.6: one trace per encounter).
        # The graph is invoked three times — once to the accept gate, once to
        # the reveal gate, once to the outcome — and without a parent span each
        # invocation would start its own trace, leaving the demo with three
        # unrelated fragments instead of one story.
        with span("encounter", encounter_id=eid, user_id=user_id, day=day.isoformat()):
            return self._drive(encounter, state, config, clock)

    def _drive(self, encounter, state, config, clock: SimClock) -> Encounter | None:
        """Drive one encounter through the graph's three stops.

        Split out from `_run_encounter` only so the whole thing sits inside one
        span; the sequence below is the encounter as the state machine sees it.
        """
        result = self.graph.invoke(state, config)
        encounter = result["encounter"]

        if encounter.state is EncounterState.ABANDONED:
            self.totals.days_without_candidate += 1
            return None

        self.totals.encounters_offered += 1
        METRICS.record_encounter_for(encounter.user_a, encounter.user_b)
        self.runtime.encounter_counts[encounter.user_a] += 1
        self.runtime.encounter_counts[encounter.user_b] += 1
        self.runtime.recent_partners.setdefault(encounter.user_a, set()).add(encounter.user_b)
        self.runtime.recent_partners.setdefault(encounter.user_b, set()).add(encounter.user_a)

        # --- gate 1: will you take the call ---------------------------
        accepts = {
            uid: "yes" if self._accepts(uid, encounter, clock) else "no"
            for uid in encounter.participants()
        }
        result = self.graph.invoke(Command(resume=accepts), config)
        encounter = result["encounter"]
        if encounter.state is EncounterState.ABANDONED:
            if "voice bridge" in result.get("terminal_reason", ""):
                self.totals.bridge_failures += 1
            return encounter
        self.totals.encounters_accepted += 1
        self.totals.calls_completed += 1

        # --- gate 2: may we swap names --------------------------------
        reveals = {
            uid: "yes" if self._says_yes(uid, encounter) else "no"
            for uid in encounter.participants()
        }
        result = self.graph.invoke(Command(resume=reveals), config)
        encounter = result["encounter"]

        if encounter.state in (EncounterState.REVEALED, EncounterState.LOCKED_IN):
            self.totals.mutual_connects += 1
            self._open_lockin(encounter, clock, result)

        if not self.demo_trace and encounter.state is EncounterState.LOCKED_IN:
            self.demo_trace = TRACES.tree(encounter.trace_id)
        # A six-week run produces hundreds of thousands of spans. The demo
        # trace above is kept; the rest are released once the day is over.
        if len(TRACES.spans) > 20000:
            TRACES.reset()
        return encounter

    def _accepts(self, user_id: str, encounter: Encounter, clock: SimClock) -> bool:
        person = self.people[user_id]
        other = self.people[encounter.other(user_id)]
        shared = set(person.user.profile.availability_window) & set(
            other.user.profile.availability_window
        )
        return self.responder.accepts_call(person, bool(shared), clock.day_index)

    def _says_yes(self, user_id: str, encounter: Encounter) -> bool:
        return self.responder.says_yes(
            self.people[user_id], self.people[encounter.other(user_id)]
        )

    # -----------------------------------------------------------------
    # Lock-ins
    # -----------------------------------------------------------------

    def _open_lockin(self, encounter: Encounter, clock: SimClock, result: dict) -> None:
        lid = result.get("lockin_id") or make_lockin_id(encounter.user_a, encounter.user_b)
        if lid in self.lockins:
            return
        now = encounter.call_ended or clock.at(19, 3)
        lockin = LockIn(
            id=lid,
            pair_id=lid,
            user_a=encounter.user_a,
            user_b=encounter.user_b,
            opened_at=now,
            last_contact=now,
            contacts=1,
        )
        self.lockins[lid] = lockin
        self.totals.lockins_opened += 1

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

    def _run_continuity(self, clock: SimClock) -> None:
        """The weekly pass. This is the "plans, acts and adapts over time" half."""
        now = clock.at(9, 0)
        for lockin in list(self.lockins.values()):
            if lockin.state is LockInState.RELEASED:
                continue
            for uid in (lockin.user_a, lockin.user_b):
                action = self.runtime.continuity.act(
                    lockin, WORLD.users[uid], clock.week_index, now
                )
                if action is None:
                    continue
                self._apply_continuity(lockin, uid, action, clock, now)

    def _apply_continuity(self, lockin, uid, action, clock: SimClock, now: datetime) -> None:
        week = clock.week_index
        if action.action == "release":
            lockin.state = LockInState.RELEASED
            lockin.released_on = clock.current
            self.totals.lockins_released += 1
            for participant in (lockin.user_a, lockin.user_b):
                user = WORLD.users[participant]
                user.lockin_slots = min(SETTINGS.rules.max_lockins, user.lockin_slots + 1)
            return

        if action.action == "adjust_pace" and action.pace_pref_days:
            lockin.pace_pref_days = action.pace_pref_days
            return

        # Did the other person actually engage? This is the simulated human
        # answering, not the agent deciding it went well.
        other = lockin.other(uid)
        pace_fit = 1.0 - min(1.0, abs((now - lockin.last_contact).days - lockin.pace_pref_days) / 7)
        if self.responder.replies_this_week(
            self.people[uid], self.people[other], week, pace_fit
        ):
            gap = max(0.5, (now - lockin.last_contact).days or 0.5)
            lockin.pace_pref_days = self.runtime.continuity.learn_pace(lockin, gap)
            lockin.last_contact = now
            lockin.contacts += 1
            lockin.state = LockInState.ACTIVE
            self._maybe_meet(lockin, uid, other, clock, action)
            self._maybe_prompt(lockin, uid, other, now)
        elif (now - lockin.last_contact).days >= SETTINGS.rules.lockin_quiet_days:
            lockin.state = LockInState.QUIET

        self._capture_example(lockin, uid, action, week)

    def _maybe_meet(self, lockin, uid, other, clock: SimClock, action) -> None:
        if lockin.met_in_person_on is not None:
            return
        proposed = action.action == "propose_meeting"
        if proposed:
            # The Date Agent turns "we should meet" into something specific.
            self.date_agent.suggest(lockin, WORLD.users[uid], WORLD.users[other])
        if self.responder.meets_in_person(
            self.people[uid], self.people[other], lockin.contacts, proposed
        ):
            lockin.met_in_person_on = clock.current
            if (clock.current - lockin.opened_at.date()).days <= 14:
                self.totals.met_in_person_by_day_14 += 1

    def _maybe_prompt(self, lockin, uid, other, now: datetime) -> None:
        """A stalling conversation gets a grounded prompt — if both opted in."""
        user, peer = WORLD.users[uid], WORLD.users[other]
        if not (
            user.consent_scope.allow_conversation_prompts
            and peer.consent_scope.allow_conversation_prompts
        ):
            return
        self.communication.suggest(lockin, user, peer, now)

    # -----------------------------------------------------------------
    def _capture_example(self, lockin, uid, action, week: int) -> None:
        """Keep one week-1 and one week-5 action for the SAME lock-in.

        The claim on the deck is that week 5 differs visibly from week 1. This
        is the evidence for it, and it is captured during the run rather than
        written afterwards.
        """
        line = (
            f"week {week} · {action.action} · {action.message}"
            + (f"  [grounded in: {action.reference}]" if action.reference else "")
        )
        if week <= 1 and not self._week_one_example:
            self._week_one_example = line
            self._example_lockin = lockin.id
            self.continuity_examples = [line]
        elif (
            week >= 5
            and self._week_one_example
            and getattr(self, "_example_lockin", None) == lockin.id
            and len(self.continuity_examples) < 2
        ):
            self.continuity_examples.append(line)

    def _finalise(self, clock: SimClock) -> None:
        week_four_cutoff = self.day_zero + timedelta(days=28)
        for lockin in self.lockins.values():
            opened = lockin.opened_at.date()
            if opened > week_four_cutoff:
                continue                               # not old enough to survive 4 weeks
            still_alive = lockin.state is not LockInState.RELEASED and (
                lockin.last_contact.date() >= week_four_cutoff
                or lockin.met_in_person_on is not None
            )
            if still_alive:
                self.totals.lockins_active_at_week_4 += 1

        if self.totals.days_without_candidate:
            self.notes.append(
                f"{self.totals.days_without_candidate} user-days ended with no "
                "eligible candidate in the overlap pool. Those are quiet days, "
                "not failures — nobody eligible crossed that person's path."
            )
        if self.totals.bridge_failures:
            self.notes.append(
                f"{self.totals.bridge_failures} encounters were abandoned because "
                "the voice bridge failed. Neither party was told the failure was "
                "ours, and the encounter is re-offered the next day."
            )
        if METRICS.llm_fallbacks:
            self.notes.append(
                f"{len(METRICS.llm_fallbacks)} decisions used the deterministic "
                "policy rather than a model (budget or model failure). Nothing "
                "was dropped; see the failures list in the metrics snapshot."
            )
