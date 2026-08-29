"""The client and the backend must agree, and this is what checks that they do.

`web/src/api/wire.ts` says: "Do not edit without editing the pydantic enum —
`spark/tests/test_wire_contract.py` fails if they drift." This is that file.

Two kinds of drift are caught here.

**Vocabulary.** The client's `Intent` and `WIRE_ENCOUNTER_STATES` are hand-typed
copies of pydantic enums. A rename on the Python side that is not mirrored would
not fail to compile on either side — `HttpAdapter` would simply stop matching,
silently, which is the worst way for a type mismatch to present itself.

**The onboarding keyword lists.** `MockAdapter` has to extract a profile with no
backend, so `web/src/api/extract.ts` reimplements the deterministic path in
`src/agents/onboarding.py`. Duplication is a drift risk, and the risk is not
cosmetic: the intent-phrase list IS the specification of "the user named it"
(ARCHITECTURE §13.1). If the two sides disagree about which phrases name an
intent, the demo and the product disagree about a safety rule.

These tests read the TypeScript as text rather than importing it. That is the
point — no build step, no node, and it fails on the source a reviewer reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents import onboarding
from src.schemas.core import EncounterState, Intent

WEB_API = Path(__file__).resolve().parents[2] / "web" / "src" / "api"
EXTRACT_TS = WEB_API / "extract.ts"
WIRE_TS = WEB_API / "wire.ts"

pytestmark = pytest.mark.skipif(
    not EXTRACT_TS.exists(),
    reason="the web client is not present in this checkout",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_array(source: str, name: str) -> list[str]:
    """The quoted strings in `export const NAME = [ ... ]`."""
    match = re.search(rf"{name}\s*=\s*\[(.*?)\]\s*as const;", source, re.S)
    assert match, f"{name} not found in the TypeScript"
    return re.findall(r'"([^"]+)"', match.group(1))


def _regex_pairs(source: str, name: str) -> list[tuple[str, str]]:
    """The `[/pattern/i, "value"]` entries of a TypeScript table."""
    match = re.search(rf"{name}[^=]*=\s*\[(.*?)\n\];", source, re.S)
    assert match, f"{name} not found in the TypeScript"
    return re.findall(r"\[/(.+?)/i,\s*\"([^\"]+)\"\]", match.group(1))


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_intent_values_match() -> None:
    """The client's `Intent` union is the pydantic enum, verbatim."""
    listed = _string_array(_source(WIRE_TS), "WIRE_INTENTS")
    assert listed == [i.value for i in Intent]


def test_encounter_states_match() -> None:
    """`WIRE_ENCOUNTER_STATES` is the backend machine, verbatim.

    The client deliberately keeps a *different, smaller* `ClientState` — see
    note 2 in wire.ts. This asserts the copy of the BACKEND's states, which is
    what actually crosses the network.
    """
    listed = _string_array(_source(WIRE_TS), "WIRE_ENCOUNTER_STATES")
    assert listed == [s.value for s in EncounterState]


# ---------------------------------------------------------------------------
# The onboarding lists
# ---------------------------------------------------------------------------


def test_known_interests_match() -> None:
    source = _source(EXTRACT_TS)
    assert _string_array(source, "KNOWN_INTERESTS") == list(
        onboarding._KNOWN_INTERESTS
    )


def test_known_values_match() -> None:
    source = _source(EXTRACT_TS)
    assert _string_array(source, "KNOWN_VALUES") == list(onboarding._KNOWN_VALUES)


def test_intent_phrases_match() -> None:
    """The list that defines "the user named an intent", on both sides.

    This is the one that matters. Every other assertion in this file is about
    data quality; this one is about two people being put in front of each other
    under a reading of their tone that neither of them agreed to.
    """
    ts = _regex_pairs(_source(EXTRACT_TS), "INTENT_PHRASES")
    py = [(pattern, intent.value) for pattern, intent in onboarding._INTENT_PHRASES]
    assert ts == py


def test_time_bucket_phrases_match() -> None:
    ts = _regex_pairs(_source(EXTRACT_TS), "BUCKET_PHRASES")
    py = [(pattern, bucket.value) for pattern, bucket in onboarding._BUCKET_PHRASES]
    assert ts == py


def test_excluded_attributes_match() -> None:
    """INVARIANT 5 — height, appearance and photographs, stripped on both sides.

    A word removed from one list and not the other means the demo captures
    something the product refuses to, or the reverse. Either way one of them is
    lying about what the profile can contain.
    """
    source = _source(EXTRACT_TS)
    match = re.search(r"EXCLUDED_ATTRIBUTES\s*=\s*\n?\s*/(.+?)/i;", source, re.S)
    assert match, "EXCLUDED_ATTRIBUTES not found in the TypeScript"
    assert match.group(1) == onboarding._EXCLUDED_ATTRIBUTES.pattern


def test_languages_match() -> None:
    source = _source(EXTRACT_TS)
    listed = _string_array(source, "LANGUAGES")
    # Mirrors the tuple inlined in `_deterministic_extract`. Read out of the
    # source rather than imported, because it is not a module constant there —
    # if that changes, this test is where the mismatch surfaces.
    python_source = Path(onboarding.__file__).read_text(encoding="utf-8")
    inline = re.search(
        r'lang for lang in \((.*?)\)', python_source, re.S
    )
    assert inline, "the language tuple moved; update this test"
    assert listed == re.findall(r'"([^"]+)"', inline.group(1))


# ---------------------------------------------------------------------------
# The call fixture
# ---------------------------------------------------------------------------

FIXTURE_TS = WEB_API / "callFixture.ts"


def test_spoken_facts_match() -> None:
    """The transcript both adapters cite must be the same transcript.

    If it is not, `MockAdapter` shows the judges one set of grounded prompts and
    the real API serves another, and only one of them has been checked.
    """
    from src.api.call_fixture import SPOKEN_FACTS

    source = _source(FIXTURE_TS)
    match = re.search(
        r"SPOKEN_FACTS: SpokenFact\[\] = \[(.*?)\n\];", source, re.S
    )
    assert match, "SPOKEN_FACTS not found in the TypeScript"
    listed = re.findall(
        r'speaker:\s*"([^"]+)",\s*topic:\s*"([^"]+)",\s*quote:\s*"([^"]+)"',
        match.group(1),
    )
    assert listed == [(f.speaker, f.topic, f.quote) for f in SPOKEN_FACTS]


def test_scripted_prompts_match() -> None:
    from src.api.call_fixture import SCRIPTED_PROMPTS

    source = _source(FIXTURE_TS)
    match = re.search(r"PROMPT_SEEDS: PromptSeed\[\] = \[(.*?)\n\];", source, re.S)
    assert match, "PROMPT_SEEDS not found in the TypeScript"
    listed = re.findall(
        r'atSecond:\s*(\d+),\s*topic:\s*"([^"]+)",\s*text:\s*"([^"]+)"',
        match.group(1),
    )
    expected = [(str(p.at_second), p.topic, p.text) for p in SCRIPTED_PROMPTS]
    assert listed == expected
