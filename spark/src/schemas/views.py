"""The only shapes a user is ever shown.

Everything a person can see in Spark is constructed as one of these models.
That is the whole point of the file: "could this leak an identity?" becomes a
question about six small classes with no free-form dict in any of them, rather
than a review of every f-string in the codebase.

Two structural guarantees live here, both of which the tests in
`tests/test_consent.py` depend on:

1. `AnonymousPeer` has nowhere to put a name, a number, a photo or a place. Not
   "we remember not to fill it in" — there is no field.

2. `CloseOutView` is built by a function that is never given the other party's
   decision, so it cannot vary with it. INVARIANT 2 is enforced by the
   signature, not by care.

British spelling throughout — Singapore convention, and it matches the
proposal.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.core import Intent, TimeBucket


class AnonymousPeer(BaseModel):
    """The other person, before a mutual reveal.

    A pseudonymous handle, what they are here for, and the coarse shape of when
    they are free. No name. No photo. No number. No age. No place, no distance,
    no cell, no time — `shared_bucket` is a time-of-day word, and it is the
    only thing said about the overlap that put these two in the same pool.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str = Field(min_length=1, max_length=32)
    intents: list[Intent]
    languages: list[str]
    #: Interests both people listed. Never the other person's full interest
    #: list — that is a fingerprint.
    shared_interests: list[str] = Field(default_factory=list, max_length=5)
    #: Coarse time-of-day only. Deliberately not a cell, a date or a place:
    #: "you were both around in the evening", never "you were both at X".
    shared_bucket: TimeBucket | None = None


class EncounterCard(BaseModel):
    """What a user sees when today's encounter is offered.

    `rationale` comes from the Match Agent and has passed the outbound
    guardrail before this object is built.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    encounter_id: str
    peer: AnonymousPeer
    rationale: str
    call_seconds: int
    respond_by: datetime
    headline: str = "Someone crossed your path today."


class ConsentPrompt(BaseModel):
    """The post-call question, asked privately of each party.

    Wording is fixed and symmetric. It never says whether the other person has
    answered, is answering, or has already answered — a "they are deciding now"
    line would be exactly the observable signal INVARIANT 2 forbids.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    encounter_id: str
    question: str = (
        "Would you like to swap names and keep talking? "
        "We will only tell either of you if you both say yes."
    )
    respond_by: datetime


class CloseOutView(BaseModel):
    """The end of an encounter that did not become a connection.

    Shown identically for every non-mutual ending: the other party declined,
    the other party never answered, this user declined, neither answered. The
    user is told the encounter is closed and that tomorrow brings another one.
    They are told nothing else, because there is nothing else it would be
    honest — or safe — to tell them.

    Note what is *not* here: no count of declines, no "they were not ready", no
    "you have been passed on N times". `available_at` is a fixed offset from
    the end of the call, so the timing carries no information either.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    encounter_id: str
    available_at: datetime
    headline: str = "That conversation has closed."
    body: str = (
        "Nothing further will be shared, in either direction. "
        "Your next encounter will be organised tomorrow."
    )


class RevealView(BaseModel):
    """The only object in the system that carries an identity.

    Constructed exclusively by `src.safety.consent.build_reveal`, which
    requires a mutual `yes` on the reveal stage. Nothing else in the codebase
    may build one — `tests/test_consent.py` checks that the construction path
    refuses every non-mutual combination.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    encounter_id: str
    lockin_id: str
    display_name: str
    #: Contact handle for the in-app channel. Still not a phone number: the
    #: reveal opens a conversation inside Spark, and personal numbers stay the
    #: users' own to give.
    contact_handle: str
    revealed_at: datetime
    headline: str = "You both said yes."


class LockInBrief(BaseModel):
    """What the Continuity Agent surfaces before the next contact.

    `grounded_in` is the note it drew on. A brief with nothing to cite is not
    sent — that is the difference between continuity and a reminder.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    lockin_id: str
    user_id: str
    message: str
    grounded_in: str
    week: int
    generated_at: datetime
