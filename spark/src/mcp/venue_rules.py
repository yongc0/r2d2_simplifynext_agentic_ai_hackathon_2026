"""What a venue is allowed to claim, and what it is allowed to carry.

Two rules, both learned from looking at what OpenStreetMap actually contains.

CONTRIBUTED FREE TEXT IS NOT OPENING HOURS

`opening_hours` is a documented syntax, and plenty of contributors ignore it.
One venue in the real fetch had, in that field, a sentence saying the place was
open by appointment, followed by a named individual and their mobile number.

The value is not reproduced here or in the tests, deliberately. Removing a
stranger's phone number from a data file and then pasting it into a docstring
would publish it more durably than leaving it alone — source code is read, and
git history is forever.

`clean_opening_hours` therefore does not sanitise — it WHITELISTS. A value is
kept only if it is recognisable opening-hours syntax; everything else becomes
`None`, which the whole system already renders as "hours unknown".

That is deliberately blunt. A cleverer parser that stripped the phone number and
kept "By appointments" would be one contributor away from the next surprise, and
the honest fallback costs us nothing: "we do not know when this is open" is a
sentence the product was already built to say.

A VENUE MAY ONLY CLAIM AN INTEREST IT PLAUSIBLY SERVES

The first version of this mapping worked off a coarse category, and tagged a
24-hour gym with `chess`, `board games` and `film`. The Date Agent grounds every
plan in an interest BOTH people listed, so that gym would have produced:

    "You have both mentioned chess, and this is something to do."

— pointing at Anytime Fitness. That is exactly the invented commonality
CLAUDE.md forbids, arrived at honestly through a lazy lookup table. The mapping
below is per OSM tag rather than per category, and where a venue type serves no
interest in the vocabulary it gets an empty tuple and is simply never suggested.
Suggesting nothing is the correct outcome; suggesting something on a false
premise is not.
"""

from __future__ import annotations

import re

#: The interest vocabulary the personas and the client share. A venue may not
#: claim anything outside it — an interest nobody can have listed is an interest
#: no plan can be grounded in.
KNOWN_INTERESTS: frozenset[str] = frozenset(
    {
        "climbing", "running", "cooking", "film", "live music", "board games",
        "cycling", "photography", "reading", "hiking", "coffee", "pottery",
        "swimming", "languages", "volunteering", "gardening", "chess",
        "baking", "football", "yoga", "birdwatching", "woodwork",
    }
)

#: What each kind of place genuinely serves. Conservative on purpose: a venue
#: that over-claims produces a plan that lies about why it was chosen, and the
#: cost of under-claiming is only that it is suggested less often.
#:
#: `bar` is deliberately narrow and `fast_food` narrower still. A hawker stall
#: is somewhere to eat, not a cooking class, and "you both mentioned cooking" is
#: a stretch even there — but it is a stretch about the FOOD, which is what the
#: stop is for, rather than a claim about an activity nobody is doing.
INTERESTS_BY_TAG: dict[str, tuple[str, ...]] = {
    "amenity=cafe": ("coffee", "reading"),
    "amenity=restaurant": ("cooking",),
    "amenity=fast_food": ("cooking",),
    "amenity=bar": ("live music",),
    "amenity=marketplace": ("cooking", "baking"),
    "tourism=museum": ("reading", "photography", "film"),
    "tourism=gallery": ("photography", "film"),
    "leisure=park": ("running", "cycling", "birdwatching", "gardening"),
    "shop=books": ("reading", "languages"),
    "leisure=fitness_centre": ("running", "swimming", "yoga"),
}

#: `24/7`, and the day/time grammar. Anything else is not opening hours as far
#: as this system is concerned.
_ALWAYS_OPEN = "24/7"

#: Day tokens, times, and the separators OSM's syntax uses. Notably ABSENT:
#: letters outside the day names, so "By appointment" and a contributor's name
#: and number cannot pass, and neither can anything else somebody types in
#: there later.
_HOURS_GRAMMAR = re.compile(
    r"^(?:"
    r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|off|open|closed)"
    r"|\d{1,2}:\d{2}"
    r"|[\s,;:\-+]"
    r")+$"
)

#: A recognisable time range has to appear somewhere, or the value says nothing
#: useful. "Mo-Su" alone is a set of days with no hours in it.
_HAS_A_TIME = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")


def clean_opening_hours(raw: str | None) -> str | None:
    """Opening hours, or `None` meaning genuinely unknown.

    A whitelist, not a scrub. See the module docstring: the value that forced
    this was a contributor's phone number, and the next surprise will be
    something nobody predicted, so anything that is not recognisable syntax is
    discarded rather than repaired.
    """
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if value == _ALWAYS_OPEN:
        return value
    if not _HOURS_GRAMMAR.match(value):
        return None
    if not _HAS_A_TIME.search(value):
        return None
    return value


def interests_for(tag: str) -> tuple[str, ...]:
    """What a venue of this OSM type may claim, filtered to the vocabulary.

    An unknown tag returns nothing rather than falling back to a generic set.
    A venue with no interests is never suggested, which is the right answer for
    a kind of place nobody has decided what to do with yet.
    """
    return tuple(
        interest
        for interest in INTERESTS_BY_TAG.get(tag, ())
        if interest in KNOWN_INTERESTS
    )


def clean_venue(venue: dict) -> dict:
    """One venue, with its hours whitelisted and its claims cut back.

    Applied on every read path rather than only at fetch time, so a file
    produced by an older version of the fetch script — or edited by hand —
    cannot get an unchecked value in front of a person.
    """
    tag = venue.get("osm_tag")
    interests = (
        list(interests_for(tag)) if tag else _fallback_interests(venue)
    )
    return {
        **venue,
        "opening_hours": clean_opening_hours(venue.get("opening_hours")),
        "interests": interests,
    }


#: (category, format, energy, budget) back to the OSM tag it came from.
#:
#: The fetch script's `QUERIES` assigns those four attributes per tag, and the
#: combinations are unique — with one harmless collision, `fast_food` and
#: `marketplace`, which are both somewhere to eat and get the same claim. So a
#: venue fetched before `osm_tag` was recorded can have its type recovered
#: exactly, and its interests corrected, WITHOUT re-fetching anything. That
#: matters: Overpass rate-limits hard enough that a re-fetch is not always
#: available, and the alternative was shipping a gym that claimed chess.
_ATTRS_TO_TAG: dict[tuple[str, str, str, str], str] = {
    ("drink", "food", "low", "under_20"): "amenity=cafe",
    ("food", "food", "low", "under_50"): "amenity=restaurant",
    ("food", "food", "low", "under_20"): "amenity=fast_food",
    ("drink", "food", "low", "under_50"): "amenity=bar",
    ("activity", "learning", "low", "under_20"): "tourism=museum",
    ("activity", "learning", "low", "free"): "tourism=gallery",
    ("activity", "outdoors", "medium", "free"): "leisure=park",
    ("activity", "activity", "low", "free"): "shop=books",
    ("activity", "activity", "high", "under_20"): "leisure=fitness_centre",
}


def _fallback_interests(venue: dict) -> list[str]:
    """Interests for a venue row fetched before `osm_tag` was recorded.

    The type is recovered from the four attributes the fetch script assigned it
    and the honest mapping is applied. A row whose attributes match nothing
    known gets NO interests — and is therefore never suggested — rather than a
    generic set, because a generic set is precisely how a gym came to claim
    that two people had both mentioned chess.
    """
    key = (
        venue.get("category", ""),
        venue.get("format", ""),
        venue.get("energy", ""),
        venue.get("budget", ""),
    )
    tag = _ATTRS_TO_TAG.get(key)
    return list(interests_for(tag)) if tag else []
