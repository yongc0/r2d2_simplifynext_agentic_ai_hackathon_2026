"""Shared fixtures.

Two personas, a clean world, and a clean metrics registry per test. Nothing
here touches the network, and nothing needs an API key: the whole suite runs on
the deterministic policy.
"""

from __future__ import annotations

import os

# BEFORE any `src` import, because `src.config` resolves the provider once, at
# import time. The suite must be hermetic: no network, no key, no cost, and the
# same result on a machine that happens to have GROQ_API_KEY in its .env as on
# one that does not. A test that quietly makes paid API calls is a test nobody
# runs. Override deliberately with SPARK_TEST_PROVIDER=groq to exercise the
# model path.
os.environ["SPARK_LLM_PROVIDER"] = os.environ.get("SPARK_TEST_PROVIDER", "deterministic")

import shutil                                        # noqa: E402
from datetime import date as Date                    # noqa: E402
from datetime import datetime                        # noqa: E402

import pytest                                        # noqa: E402

from src.clock import SimClock          # noqa: E402
from src.config import RUNS_DIR
from src.ids import encounter_id, handle_for_index
from src.mcp.registry import MCPClient
from src.mcp.services import WORLD
from src.safety.consent import ConsentLedger
from src.safety.guardrails import IDENTITIES
from src.safety.trust import TrustAndSafety
from src.schemas.core import (
    ConsentScope,
    Encounter,
    Intent,
    PrivateIdentity,
    Profile,
    TimeBucket,
    User,
    VerificationTier,
)
from src.telemetry.metrics import METRICS

DAY = Date(2026, 9, 1)
CALL_ENDED = datetime(2026, 9, 1, 19, 3)


def make_user(
    user_id: str,
    index: int,
    name: str,
    intents: list[Intent] | None = None,
    interests: list[str] | None = None,
    languages: list[str] | None = None,
    buckets: list[TimeBucket] | None = None,
) -> User:
    return User(
        id=user_id,
        identity=PrivateIdentity(
            display_name=name,
            phone=f"+6590000{index:03d}",
            email=f"{user_id}@example.invalid",
        ),
        profile=Profile(
            user_id=user_id,
            intents=intents or [Intent.PARTNER_LONG_TERM],
            interests=interests or ["climbing", "film"],
            values=["honesty"],
            languages=languages or ["English"],
            availability_window=buckets or [TimeBucket.EVENING],
        ),
        consent_scope=ConsentScope(
            user_id=user_id,
            matchable_fields=["intents", "interests", "values", "languages",
                              "availability_window", "age_band"],
        ),
        verification_tier=VerificationTier.PHONE,
        handle=handle_for_index(index),
    )


@pytest.fixture(autouse=True)
def clean_registries():
    """Every test starts from zero.

    `METRICS` and `IDENTITIES` are process-wide singletons on purpose — the
    guardrail must see every user in the run, not just the two in front of it —
    so the reset belongs here rather than in each test.
    """
    METRICS.reset()
    IDENTITIES.reset()
    WORLD.reset()
    yield
    METRICS.reset()
    IDENTITIES.reset()
    WORLD.reset()


@pytest.fixture
def alice() -> User:
    return make_user("u-alice", 0, "Elowen Brackley")


@pytest.fixture
def bob() -> User:
    return make_user("u-bob", 1, "Torin Kilbride")


@pytest.fixture
def users(alice: User, bob: User) -> dict[str, User]:
    for user in (alice, bob):
        IDENTITIES.register(user)
        WORLD.users[user.id] = user
    return {alice.id: alice, bob.id: bob}


@pytest.fixture
def ledger() -> ConsentLedger:
    return ConsentLedger()


@pytest.fixture
def trust() -> TrustAndSafety:
    return TrustAndSafety()


@pytest.fixture
def client() -> MCPClient:
    return MCPClient()


@pytest.fixture
def clock() -> SimClock:
    return SimClock(DAY)


@pytest.fixture
def encounter(users) -> Encounter:
    """An encounter that has already had its call, ready for the reveal gate."""
    ids = sorted(users)
    enc = Encounter(
        id=encounter_id(DAY.isoformat(), ids[0], ids[1]),
        match_id="match-test",
        day=DAY,
        user_a=ids[0],
        user_b=ids[1],
    )
    enc.call_started = datetime(2026, 9, 1, 19, 0)
    enc.call_ended = CALL_ENDED
    enc.call_duration_s = 180
    return enc


@pytest.fixture
def scratch_dir(request):
    """A writable directory owned by this project, for the durable-checkpoint test.

    Deliberately not pytest's `tmp_path`. That lives under the user's Temp
    directory, which is not writable by the running account on at least one
    machine here — and a durable-checkpoint test that fails for that reason
    tells you nothing about the checkpointer. `runs/` is ours and is gitignored.
    """
    path = RUNS_DIR / "test-scratch" / request.node.name
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)
