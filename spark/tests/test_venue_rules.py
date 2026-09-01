"""What a venue may carry, and what it may claim.

Both rules here exist because the real OpenStreetMap fetch broke them. These
are regression tests for things that actually happened, not hypotheticals.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.mcp.venue_rules import clean_opening_hours, clean_venue, interests_for

DATA = Path(__file__).resolve().parents[1] / "data" / "venues_osm.json"


# ---------------------------------------------------------------------------
# Contributed free text is not opening hours
# ---------------------------------------------------------------------------


def test_a_contributors_phone_number_never_survives():
    """The shape of the value the real fetch returned.

    One venue's `opening_hours` held a sentence about appointments followed by
    a named individual and their mobile number. It was in the venue file and one
    commit from a public repository and a JavaScript bundle.

    The real string is NOT reproduced here. A test that pasted it in would
    publish the number more durably than the data file did — tests are read, and
    git history does not forget. This stand-in has the same shape, and the
    whitelist rejects it for the same reason: it is not opening hours.
    """
    assert clean_opening_hours("|| By appointments. Call Sam +65 90000000") is None
    assert clean_opening_hours("open when you ring 98765432") is None


@pytest.mark.parametrize(
    "raw",
    [
        '"By appointment"',
        "Call us",
        "ring ahead 91234567",
        "Mo-Su",                 # days with no hours says nothing
        "see website",
        "",
        None,
    ],
)
def test_anything_that_is_not_hours_becomes_unknown(raw):
    """A whitelist, not a scrub.

    Repairing free text would be one contributor away from the next surprise.
    "We do not know when this is open" is a sentence the product was already
    built to say, so discarding costs nothing.
    """
    assert clean_opening_hours(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "24/7",
        "Mo-Su 09:00-18:00",
        "Mo-Fr 12:00-20:00; Sa 00:30-14:30; Su,PH off",
        "Tu-Sa 10:00-19:00; Su 10:00-17:00; Mo off",
    ],
)
def test_real_opening_hours_are_kept(raw):
    """The whitelist must not be so tight that it throws away good data —
    otherwise every stop reads "hours unknown" and the honest state becomes
    indistinguishable from a broken one."""
    assert clean_opening_hours(raw) == raw


# ---------------------------------------------------------------------------
# A venue may only claim an interest it plausibly serves
# ---------------------------------------------------------------------------


def test_a_gym_does_not_claim_chess():
    """The other thing the real fetch produced.

    The first mapping keyed interests off a coarse category and gave every
    `activity` venue `chess`, `board games` and `film`. Because the Date Agent
    grounds every plan in an interest BOTH people listed, a 24-hour gym would
    have produced "You have both mentioned chess, and this is something to do."
    That is the invented commonality CLAUDE.md forbids, reached through a lazy
    lookup table rather than a model.
    """
    gym = {
        "name": "Dennis Gym",
        "category": "activity",
        "format": "activity",
        "energy": "high",
        "budget": "under_20",
        "opening_hours": "24/7",
        "interests": ["board games", "chess", "film", "photography", "reading"],
    }
    claimed = clean_venue(gym)["interests"]
    assert "chess" not in claimed
    assert "board games" not in claimed
    assert "film" not in claimed
    # And it still claims something true, so it remains usable.
    assert "running" in claimed


def test_an_unknown_venue_type_claims_nothing():
    """No generic fallback. A venue nobody has decided what to do with is never
    suggested, which is right — the alternative is suggesting it on a false
    premise."""
    assert interests_for("amenity=nightclub") == ()
    mystery = {"category": "activity", "format": "unheard_of", "energy": "low",
               "budget": "free", "interests": ["chess"]}
    assert clean_venue(mystery)["interests"] == []


# ---------------------------------------------------------------------------
# The committed file itself
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DATA.exists(), reason="venues not fetched on this machine")
def test_the_committed_venue_file_carries_no_contact_details():
    """This file goes into a public repository. It must not carry a stranger's
    phone number, whoever typed it into OpenStreetMap."""
    text = DATA.read_text(encoding="utf-8")
    assert not re.search(r"\+\d[\d\s-]{7,}", text), (
        "a phone-like number is in the committed venue file"
    )


@pytest.mark.skipif(not DATA.exists(), reason="venues not fetched on this machine")
def test_every_committed_venue_is_already_clean():
    """Cleaning happens on read, so a dirty file is survivable — but it should
    not be committed dirty, and this is what notices if one is."""
    venues = json.loads(DATA.read_text(encoding="utf-8"))["venues"]
    for venue in venues:
        cleaned = clean_venue(venue)
        assert cleaned["opening_hours"] == venue.get("opening_hours"), venue["name"]
        assert cleaned["interests"] == venue.get("interests"), venue["name"]
