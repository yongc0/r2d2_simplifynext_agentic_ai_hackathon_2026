"""Internal shapes -> wire shapes. The one place the translation happens.

The client's `web/src/api/wire.ts` documents four differences between
FRONTEND.md's draft types and the pydantic schemas. This is the server-side
counterpart: the same four decisions, applied once, here.

Nothing in `src/api/routes/` builds a wire model by hand — every one of them
comes through a function in this file, so a field that must never be sent
cannot be sent by an endpoint that forgot.
"""

from __future__ import annotations

from src.api.schemas import EncounterCardOut, RevealOut
from src.schemas.core import Encounter, TimeBucket, User
from src.schemas.views import RevealView

#: A coarse time bucket, rendered into words.
#:
#: This function IS invariant 1 at the API boundary. The backend holds a
#: `TimeBucket` enum — never a place, never a timestamp — and the only thing
#: permitted to leave is one of these phrases. There is deliberately no branch
#: here that produces a location, because there is no location to produce.
_BUCKET_PHRASES: dict[str, str] = {
    "early_morning": "Your paths crossed early this morning",
    "morning": "Your paths crossed this morning",
    "midday": "Your paths crossed around midday",
    "afternoon": "Your paths crossed this afternoon",
    "evening": "Your paths crossed this evening",
    "night": "Your paths crossed late tonight",
}


def overlap_hint_for(bucket: TimeBucket | str | None) -> str:
    if bucket is None:
        return "Your paths crossed today"
    key = bucket.value if isinstance(bucket, TimeBucket) else str(bucket)
    return _BUCKET_PHRASES.get(key, "Your paths crossed today")


def encounter_card_out(
    encounter: Encounter,
    viewer: User,
    peer: User,
    *,
    shared_bucket: TimeBucket | None,
    window_closes_at: str,
    call_seconds: int,
    client_state: str = "NOTIFIED",
) -> EncounterCardOut:
    """Build the card the client renders.

    Note what is read off `peer` and what is not. `peer.handle` and the
    INTERSECTION of the two interest lists go out. `peer.identity` is right
    there on the object and never touched — and `EncounterCardOut` has no field
    that could hold it if it were.

    The interests are intersected rather than sent whole: one person's full
    interest list is a fingerprint, and two people can compare notes.
    """
    shared = sorted(set(viewer.profile.interests) & set(peer.profile.interests))
    return EncounterCardOut(
        encounter_id=encounter.id,
        state=client_state,                              # type: ignore[arg-type]
        intent=peer.profile.intents[0].value,            # type: ignore[arg-type]
        handle=peer.handle,
        shared_interests=shared[:5],
        overlap_hint=overlap_hint_for(shared_bucket),
        window_closes_at=window_closes_at,
        call_seconds=call_seconds,
    )


def reveal_out(view: RevealView, peer: User, shared_interests: list[str]) -> RevealOut:
    """The only function here that emits an identity.

    It takes a `RevealView`, which `src.safety.consent.build_reveal` is the sole
    constructor of, and which cannot be built without a mutual yes. So the only
    route to this function's output runs through the consent gate.
    """
    return RevealOut(
        person_id=peer.id,
        display_name=view.display_name,
        # The handle seeds the generated illustration. A stable, non-identifying
        # value — never a photograph, and never derived from the name.
        avatar_seed=peer.handle,
        shared_interests=shared_interests[:5],
    )


def reveal_out_from_user(other, shared_interests: list[str]) -> RevealOut:
    """A revealed person, for a lock-in that is already open.

    Separate from `reveal_out` on purpose. That one takes a `RevealView`, which
    only `build_reveal` can construct and only after a mutual yes — the right
    shape for the moment of reveal. A lock-in has already passed that gate, and
    re-deriving the view from a ledger lookup on every list render would be
    slower and no safer.

    The gate is upstream, where it belongs: nothing puts a `LockIn` in the store
    without `reveal_permitted` returning true.
    """
    return RevealOut(
        person_id=other.id,
        display_name=other.identity.display_name,
        avatar_seed=other.handle,
        shared_interests=list(shared_interests),
    )
