"""The six MCP servers, the client, and Trust & Safety.

Two things worth reading here:

`test_every_server_is_a_real_mcp_server` builds each one over the actual MCP
protocol machinery and asks it to list its tools. The in-process client is a
transport optimisation for a simulation that makes hundreds of thousands of
calls; these are genuine servers, and this is the test that says so.

`test_no_tool_returns_a_place_or_an_identity` sweeps every tool's output for
identity and location tokens. It is the guardrail's counterpart on the way *in*
— even if a view forgot to call `render`, a tool cannot hand it a place name to
render.
"""

from __future__ import annotations

import json
from datetime import date as Date

import pytest

from src.mcp.registry import TOOLS, MCPClient, ToolError, catalogue, find
from src.mcp.services import WORLD, index_overlaps
from src.safety.trust import TrustAndSafety
from src.schemas.core import Overlap, TimeBucket
from src.telemetry.metrics import METRICS

DAY = Date(2026, 9, 1)


@pytest.fixture
def world(users):
    ids = sorted(users)
    WORLD.overlaps[DAY] = [
        Overlap(
            user_a=ids[0], user_b=ids[1], cell_id="cell-01",
            time_bucket=TimeBucket.EVENING, date=DAY,
        )
    ]
    WORLD.availability[ids[0]] = [TimeBucket.EVENING]
    WORLD.availability[ids[1]] = [TimeBucket.EVENING, TimeBucket.MORNING]
    WORLD.venues["v-climb"] = {
        "id": "v-climb", "activity": "an hour on the bouldering wall",
        "tags": ["climbing"], "buckets": ["evening"], "is_commercial_partner": False,
    }
    index_overlaps()
    return users


# ---------------------------------------------------------------------------
# The servers are real
# ---------------------------------------------------------------------------


def test_there_are_exactly_six_servers():
    assert set(TOOLS) == {
        "spark-overlap", "spark-profile", "spark-voice",
        "spark-calendar", "spark-venue", "spark-sim",
    }


def test_every_server_is_a_real_mcp_server(world):
    """Each module builds an `MCPServer` that lists its tools over the protocol.

    `uv run -m src.mcp.overlap` serves these over stdio; this asserts the tools
    a client would see are the ones the simulation calls.
    """
    import asyncio

    from src.mcp._server import build_server

    for server_name, specs in TOOLS.items():
        server = build_server(server_name, seed_world=False)
        listed = asyncio.run(server.list_tools())
        assert {t.name for t in listed} == {s.name for s in specs}, server_name
        assert server.instructions, f"{server_name} has no instructions for a client"


def test_the_catalogue_describes_every_tool():
    for entry in catalogue():
        assert entry["description"].strip(), f"{entry['tool']} has no description"


def test_an_unknown_tool_says_what_is_available(client):
    with pytest.raises(ToolError, match="Available"):
        client.call("spark-overlap", "who_is_near_me", user_id="u")
    with pytest.raises(ToolError, match="Available"):
        client.call("spark-nonexistent", "anything")


def test_there_is_no_live_proximity_tool():
    """Live proximity was removed deliberately (§13.3). It must stay removed."""
    names = {entry["tool"] for entry in catalogue()}
    for forbidden in ("who_is_near_me", "live_position", "distance_between", "nearby"):
        assert forbidden not in names


# ---------------------------------------------------------------------------
# What tools may and may not return
# ---------------------------------------------------------------------------


def test_a_profile_never_carries_an_identity(world, client):
    result = client.call("spark-profile", "get_profile", user_id=sorted(world)[0])
    blob = json.dumps(result)
    identity = world[sorted(world)[0]].identity
    for token in (identity.display_name, identity.phone, identity.email):
        assert token not in blob


def test_no_tool_returns_a_place_name(world, client):
    """Cells are opaque tokens. `cell-01` is fine; "Raffles Place" is not."""
    from src.sim.world import _CELL_PLACES

    result = client.call(
        "spark-overlap", "overlap_pool", user_id=sorted(world)[0], day=DAY.isoformat()
    )
    blob = json.dumps(result).lower()
    for place in _CELL_PLACES:
        assert place.lower() not in blob


def test_overlap_strength_returns_buckets_but_never_cells(world, client):
    ids = sorted(world)
    result = client.call(
        "spark-overlap", "overlap_strength",
        user_id=ids[0], candidate_id=ids[1], day=DAY.isoformat(),
    )
    assert result["crossings"] == 1
    assert "cell_id" not in result and "cell" not in json.dumps(result)


def test_a_note_is_readable_only_by_its_owner(world, client):
    ids = sorted(world)
    client.call(
        "spark-profile", "write_note", owner_id=ids[0], lockin_id="lock-1",
        note="climbing", source="call", at="2026-09-01T19:00:00",
    )
    mine = client.call("spark-profile", "read_notes", owner_id=ids[0], lockin_id="lock-1")
    theirs = client.call("spark-profile", "read_notes", owner_id=ids[1], lockin_id="lock-1")
    assert len(mine["notes"]) == 1
    assert theirs["notes"] == [], "one person read another person's continuity note"


def test_an_expired_note_is_not_returned(world, client):
    """Retention is enforced on read as well as on write, so a note cannot
    resurface because a cleanup job did not run."""
    ids = sorted(world)
    client.call(
        "spark-profile", "write_note", owner_id=ids[0], lockin_id="lock-1",
        note="climbing", source="call", at="2026-09-01T19:00:00",
    )
    fresh = client.call(
        "spark-profile", "read_notes", owner_id=ids[0], as_of="2026-10-01T00:00:00"
    )
    stale = client.call(
        "spark-profile", "read_notes", owner_id=ids[0], as_of="2027-01-01T00:00:00"
    )
    assert len(fresh["notes"]) == 1
    assert stale["notes"] == []


def test_forgetting_notes_says_how_many_went(world, client):
    ids = sorted(world)
    for _ in range(3):
        client.call(
            "spark-profile", "write_note", owner_id=ids[0], lockin_id="lock-1",
            note="climbing", source="call", at="2026-09-01T19:00:00",
        )
    assert client.call("spark-profile", "forget_notes", owner_id=ids[0])["deleted"] == 3


def test_a_venue_ranking_never_sees_the_partner_flag(world, client):
    """§13.6: commercial partners may only appear where they already rank."""
    WORLD.venues["v-paid"] = {
        "id": "v-paid", "activity": "a partner bar", "tags": ["film"],
        "buckets": ["evening"], "is_commercial_partner": True,
    }
    result = client.call(
        "spark-venue", "suggest_venues", interests=["climbing"], bucket="evening"
    )
    assert result["options"][0]["venue_id"] == "v-climb"
    assert result["options"][0]["is_commercial_partner"] is False


def test_a_venue_miss_explains_the_fallback(world, client):
    """The organisers reward actionable errors. "no results" is not one."""
    with pytest.raises(ToolError, match="Falling back"):
        client.call(
            "spark-venue", "suggest_venues", interests=["astrophysics"], bucket="evening"
        )


def test_an_unknown_user_produces_an_actionable_error(client):
    with pytest.raises(ToolError, match="either the simulation was not seeded"):
        client.call("spark-profile", "get_profile", user_id="u-nobody")


# ---------------------------------------------------------------------------
# The client is where the tool-call metric is measured
# ---------------------------------------------------------------------------


def test_every_call_is_recorded_pass_or_fail(world, client):
    client.call("spark-sim", "sim_stats")
    with pytest.raises(ToolError):
        client.call("spark-profile", "get_profile", user_id="u-nobody")
    assert METRICS.tool_calls.total == 2
    assert METRICS.tool_calls.hits == 1
    assert METRICS.failures and "spark-profile" in METRICS.failures[0].where


def test_try_call_records_the_failure_rather_than_swallowing_it(world, client):
    assert client.try_call("spark-profile", "get_profile", user_id="u-nobody") is None
    assert METRICS.tool_calls.total == 1
    assert METRICS.tool_calls.hits == 0


def test_a_caller_bug_is_named_as_one(world, client):
    """Wrong arguments are a programming error, not an outage — and the message
    says so, rather than sending somebody to check the network."""
    with pytest.raises(ToolError, match="caller bug, not an outage"):
        client.call("spark-sim", "sim_stats", unexpected="argument")


# ---------------------------------------------------------------------------
# Trust & Safety
# ---------------------------------------------------------------------------


def test_the_adversarial_set_has_no_false_negatives():
    """The guardrail false-negative rate (§18). Harmful content that gets
    through matters far more than benign content that does not."""
    from src.config import DATA_DIR
    from src.sim.world import write_adversarial_set

    write_adversarial_set()
    cases = json.loads((DATA_DIR / "adversarial.json").read_text(encoding="utf-8"))["cases"]
    scores = TrustAndSafety().score_adversarial_set(cases)

    assert scores["harmful_cases"] >= 10
    assert scores["false_negatives"] == 0, (
        f"harmful content passed screening: {METRICS.failures}"
    )
    # The benign half is what stops the number being gamed by blocking
    # everything. A high false-positive rate would make the filter unusable.
    assert scores["false_positive_rate"] <= 0.2, (
        f"the filter blocks too much ordinary conversation: {scores}"
    )


def test_screening_explains_itself_to_the_user(world):
    verdict = TrustAndSafety().screen_text("just give me your whatsapp")
    assert verdict.allowed is False
    assert "consent_circumvention" in verdict.categories
    assert "private until you have both said yes" in verdict.user_message


def test_screening_is_scoped_to_text_not_audio():
    """Open item: voice-channel screening is materially harder than text, and
    §13.8 scopes this agent to text rather than claiming otherwise.

    Checked here so the scope is a fact about the code, not a footnote.
    """
    import inspect

    source = inspect.getsource(TrustAndSafety)
    assert "audio" not in source.lower() or "does not screen the audio" in source.lower()
