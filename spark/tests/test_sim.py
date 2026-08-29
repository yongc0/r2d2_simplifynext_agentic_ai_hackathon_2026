"""The simulator, the AG-UI surface, and the evaluation's integrity.

The most important test in this file is
`test_no_agent_can_read_the_simulator`. The whole three-arm comparison rests on
the latent affinities being unobservable: an agent that could read them would
be cheating at its own evaluation, and the result would be worthless. That is
checked against the imports rather than trusted.
"""

from __future__ import annotations

import ast
import random
import statistics
from datetime import date as Date
from pathlib import Path

import pytest

from src import agui
from src.schemas.views import CloseOutView, RevealView
from src.sim.personas import generate_personas, latent_affinity
from src.sim.responder import Responder
from src.sim.transcripts import silent_on_intent_transcript, transcript_for
from src.sim.world import SimWorldBuilder

DAY_ZERO = Date(2026, 9, 1)


# ---------------------------------------------------------------------------
# The evaluation's integrity
# ---------------------------------------------------------------------------


def test_no_decision_making_code_imports_the_simulator():
    """The agent, graph and safety layers must not import from `src/sim/`.

    Those are the layers that decide things. `src/mcp/` is deliberately not on
    this list: `_server.py` imports the simulator to *populate its data store*
    when a server is run standalone, so that an MCP client connecting to
    `spark-overlap` gets real data rather than an empty store. It serves the
    observable half only — `get_profile` returns no identity and no latent
    trait, and `tests/test_mcp.py` checks that.

    The sharper claim is the next test: nothing outside `src/sim/` reads a
    latent trait at all.
    """
    offenders: list[str] = []
    for directory in ("src/agents", "src/graph", "src/safety"):
        for path in Path(directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                if module.startswith("src.sim"):
                    offenders.append(f"{path.as_posix()}:{node.lineno} imports {module}")
    assert not offenders, (
        "decision-making code can see the simulator: " + "; ".join(offenders)
    )


def test_nothing_outside_the_simulator_reads_a_latent_trait():
    """The invariant the three-arm comparison actually rests on.

    `Persona.latent` and `latent_affinity` are the answer sheet. Only
    `src/sim/responder.py` — which plays the simulated humans — may read them.
    An agent, an arm, a metric or a CLI that touched them would be scoring
    itself against something it could see, and every number would be worthless.
    """
    allowed = {"src/sim/personas.py", "src/sim/responder.py", "src/sim/world.py"}
    offenders: list[str] = []
    for directory in ("src", "eval"):
        for path in Path(directory).rglob("*.py"):
            if path.as_posix() in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "latent":
                    offenders.append(f"{path.as_posix()}:{node.lineno} reads .latent")
                if isinstance(node, ast.Name) and node.id == "latent_affinity":
                    offenders.append(
                        f"{path.as_posix()}:{node.lineno} calls latent_affinity"
                    )
    assert not offenders, (
        "the simulator's ground truth is read outside src/sim/: "
        + "; ".join(offenders)
    )


def test_stated_interests_carry_a_weak_but_real_signal():
    """The premise the whole comparison rests on.

    If shared interests told you *nothing* about latent affinity, the Match
    Agent could not beat random assignment however good it was, and a
    pre-registered comparison that can only come out one way is not a test. If
    they told you a great deal, the Match Agent would win by construction and
    the result would be equally worthless.

    So the correlation must be positive and small.
    """
    personas = generate_personas(200, seed=42)
    rng = random.Random(0)
    shared, affinity = [], []
    for _ in range(4000):
        a, b = rng.sample(personas, 2)
        shared.append(len(set(a.user.profile.interests) & set(b.user.profile.interests)))
        affinity.append(latent_affinity(a, b))

    mean_shared = statistics.mean(shared)
    mean_affinity = statistics.mean(affinity)
    covariance = sum(
        (s - mean_shared) * (x - mean_affinity) for s, x in zip(shared, affinity)
    ) / len(shared)
    correlation = covariance / (
        statistics.pstdev(shared) * statistics.pstdev(affinity)
    )
    assert 0.01 < correlation < 0.25, (
        f"correlation between shared interests and latent affinity is "
        f"{correlation:.3f}. Below ~0.01 the matcher cannot beat chance by "
        "construction; above ~0.25 it wins by construction. Either way the "
        "evaluation would stop being evidence."
    )


def test_the_same_seed_produces_the_same_world():
    """A six-week run must be reproducible from one integer."""
    a = generate_personas(50, seed=7)
    b = generate_personas(50, seed=7)
    c = generate_personas(50, seed=8)
    assert [p.user.model_dump() for p in a] == [p.user.model_dump() for p in b]
    assert [p.latent for p in a] == [p.latent for p in b]
    assert [p.user.model_dump() for p in a] != [p.user.model_dump() for p in c]


def test_the_responder_is_not_symmetric():
    """Each person decides separately after the call.

    A mutual yes needs two independent decisions to land, which is why the
    mutual connect rate is so much lower than the individual yes rate — in the
    simulation and in life.
    """
    personas = generate_personas(40, seed=3)
    responder = Responder(rng=random.Random(11))
    a, b = personas[0], personas[1]
    outcomes = {(responder.says_yes(a, b), responder.says_yes(b, a)) for _ in range(200)}
    assert len(outcomes) > 1, "both sides answered identically every time"


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------


def test_overlaps_are_built_from_routines_not_random_pairing():
    """Two people who commute alike should keep appearing in each other's pool.

    Random pairing would make "your paths crossed" meaningless — the whole
    proposition is that the coincidence is real.
    """
    builder = SimWorldBuilder(seed=5, persona_count=80)
    builder.build(day_zero=DAY_ZERO, days=14)
    from src.mcp.services import WORLD

    repeat_pairs = sum(1 for crossings in WORLD.crossings.values() if len(crossings) > 3)
    assert repeat_pairs > 0, "no pair crossed paths repeatedly; overlap is not routine-driven"


def test_a_person_never_overlaps_with_themselves():
    builder = SimWorldBuilder(seed=9, persona_count=60)
    builder.build(day_zero=DAY_ZERO, days=7)
    from src.mcp.services import WORLD

    for overlaps in WORLD.overlaps.values():
        for overlap in overlaps:
            assert overlap.user_a != overlap.user_b


def test_the_cell_index_matches_the_overlaps_it_was_built_from():
    builder = SimWorldBuilder(seed=4, persona_count=50)
    builder.build(day_zero=DAY_ZERO, days=10)
    from src.mcp.services import WORLD

    counted = sum(len(v) for v in WORLD.crossings.values())
    stored = sum(len(v) for v in WORLD.overlaps.values())
    assert counted == stored


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


def test_a_transcript_carries_the_things_the_extraction_must_ignore():
    """A demo where the tricky cases never appear demonstrates nothing."""
    personas = generate_personas(20, seed=2)
    transcripts = [transcript_for(p, random.Random(i)) for i, p in enumerate(personas)]
    joined = " ".join(transcripts).lower()
    assert "tall" in joined or "photograph" in joined, "no appearance aside anywhere"
    assert "serious but" in joined or "tired of it" in joined, "no misleading tone anywhere"


def test_the_silent_transcript_names_no_intent():
    from src.agents.onboarding import _named_intents

    assert _named_intents(silent_on_intent_transcript()) == ()


def test_a_transcript_is_stable_for_a_given_seed():
    personas = generate_personas(5, seed=1)
    first = transcript_for(personas[0], random.Random(99))
    second = transcript_for(personas[0], random.Random(99))
    assert first == second


# ---------------------------------------------------------------------------
# AG-UI
# ---------------------------------------------------------------------------


def test_a_close_out_offers_no_actions():
    """A "why?" button would be a request for exactly the information
    INVARIANT 2 exists to withhold."""
    from datetime import datetime

    view = CloseOutView(encounter_id="e", available_at=datetime(2026, 9, 1, 20, 3))
    directive = agui.close_out(view, "u-alice")
    assert directive.actions == []
    assert directive.blocking is False


def test_a_consent_prompt_offers_exactly_two_actions():
    """No "maybe", no "see who it is first", no "tell me if they said yes"."""
    from datetime import datetime

    from src.schemas.views import ConsentPrompt

    directive = agui.consent_prompt(
        ConsentPrompt(encounter_id="e", respond_by=datetime(2026, 9, 2, 19, 3)), "u-alice"
    )
    assert directive.actions == ["yes", "no"]
    assert directive.blocking is True


def test_outcome_directives_dispatch_on_type_not_on_a_flag():
    """A `CloseOutView` cannot be rendered as a reveal, because it has no
    identity to put in one."""
    from datetime import datetime

    views = {
        "u-alice": RevealView(
            encounter_id="e", lockin_id="l", display_name="Elowen Brackley",
            contact_handle="spark:azure-heron", revealed_at=datetime(2026, 9, 1, 20, 3),
        ),
        "u-bob": CloseOutView(encounter_id="e", available_at=datetime(2026, 9, 1, 20, 3)),
    }
    directives = {d.audience: d for d in agui.directives_for_outcome(views)}
    assert directives["u-alice"].component == "reveal"
    assert directives["u-bob"].component == "close_out"
    assert "display_name" not in directives["u-bob"].data


def test_every_directive_names_its_audience():
    """A client must never render a directive to anyone else."""
    from datetime import datetime

    directive = agui.notice("That message was not sent.", "u-alice")
    assert directive.audience == "u-alice"
    assert directive.component == "notice"
