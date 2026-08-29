"""Identifiers, and the pseudonymous handles a person is known by before a reveal.

A handle has one job: let two strangers refer to each other for three minutes
without either learning anything. So it is drawn from a fixed word list rather
than derived from the name — a handle computed from "Marcus Tay" is a hash of
an identity, and hashes of small domains are not anonymous.

Handles are stable per user (the same person is the same handle in every
encounter, which is what makes a lock-in coherent) and assigned by index, so
two users never collide inside one simulation run.
"""

from __future__ import annotations

import hashlib

#: Deliberately ordinary, unloaded words. A handle should carry no flattery, no
#: implied gender and no hint of a personality — those are all things the other
#: person is supposed to find out by talking.
_COLOURS = (
    "amber", "azure", "cobalt", "copper", "coral", "indigo", "ivory", "jade",
    "lilac", "olive", "russet", "saffron", "sepia", "slate", "teal", "umber",
)
_CREATURES = (
    "heron", "otter", "sparrow", "marten", "gannet", "ibis", "lynx", "oriole",
    "plover", "swift", "tapir", "vireo", "wren", "civet", "dunlin", "egret",
)


def handle_for_index(index: int) -> str:
    """A stable, collision-free handle for the nth user.

    16 x 16 = 256 unique pairs before the numeric suffix appears, which covers
    the 200-persona simulation with no repeats. Above that the suffix keeps it
    unique rather than letting two people share a handle — two identical
    handles in one pool would be a genuine confusion, not a cosmetic one.
    """
    if index < 0:
        raise ValueError("handle index must not be negative")
    colour = _COLOURS[index % len(_COLOURS)]
    creature = _CREATURES[(index // len(_COLOURS)) % len(_CREATURES)]
    cycle = index // (len(_COLOURS) * len(_CREATURES))
    suffix = "" if cycle == 0 else f"-{cycle + 1}"
    return f"{colour}-{creature}{suffix}"


def pair_id(user_a: str, user_b: str) -> str:
    """A stable id for an unordered pair.

    Sorted before hashing so (a, b) and (b, a) are the same lock-in, and
    truncated because this is an identifier, not a signature.
    """
    lo, hi = sorted((user_a, user_b))
    digest = hashlib.sha256(f"{lo}|{hi}".encode()).hexdigest()
    return f"pair-{digest[:12]}"


def encounter_id(day: str, user_a: str, user_b: str) -> str:
    """One encounter per pair per day, so the id is derivable and idempotent —
    replaying a day cannot create a duplicate encounter."""
    lo, hi = sorted((user_a, user_b))
    digest = hashlib.sha256(f"{day}|{lo}|{hi}".encode()).hexdigest()
    return f"enc-{day}-{digest[:8]}"


def match_id(day: str, user_id: str) -> str:
    """One selection per user per day."""
    return f"match-{day}-{user_id}"


def lockin_id(user_a: str, user_b: str) -> str:
    return f"lock-{pair_id(user_a, user_b)[5:]}"


def note_id(lockin: str, owner: str, seq: int) -> str:
    return f"note-{lockin[5:]}-{owner}-{seq}"
