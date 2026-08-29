"""The AG-UI surface — the agent decides what to render.

docs/ARCHITECTURE.md §16 lists AG-UI as the client: rather than a fixed set of
screens that poll for state, the agent emits a typed instruction saying what to
put in front of the person right now.

This module is the boundary. It turns the objects in `src/schemas/views.py`
into `RenderDirective`s a client can draw, and it is deliberately the *only*
place that mapping exists.

Why that matters more here than in most products: a client that renders from
raw state can render whatever the state happens to contain, which is how an
identity ends up on a screen by accident. A client that renders only what this
module emits can only show what a view object holds — and the view objects have
no field for a name, a place or a distance before a mutual reveal.

The directives are plain data. A React, Flutter or terminal client consumes the
same stream; `src/cli/encounter.py --agui` prints it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.schemas.views import (
    CloseOutView,
    ConsentPrompt,
    EncounterCard,
    LockInBrief,
    RevealView,
)

#: What a client is being asked to draw. A closed set: a directive a client
#: does not recognise is a bug, not a fallback to raw JSON.
Component = Literal[
    "encounter_card",       # today's anonymous encounter
    "consent_prompt",       # a gate: two buttons, no third option
    "close_out",            # the silent ending
    "reveal",               # the only component that carries an identity
    "brief",                # what the pair last discussed
    "notice",               # plain text, for safety messages
]


@dataclass
class RenderDirective:
    """One instruction: draw this component, with this data, for this person."""

    component: Component
    #: Who this is for. A client must never render a directive to anyone else.
    audience: str
    data: dict[str, Any]
    #: Actions the person may take. Empty means the directive is informational.
    #: Note there is no "see who this is" action anywhere except after a reveal.
    actions: list[str] = field(default_factory=list)
    #: Whether the graph is waiting on this. True for the two consent gates —
    #: the client is looking at a halted graph, not a loading spinner.
    blocking: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def encounter_card(view: EncounterCard, audience: str) -> RenderDirective:
    return RenderDirective(
        component="encounter_card",
        audience=audience,
        data=view.model_dump(mode="json"),
        actions=["accept", "decline"],
        blocking=True,
    )


def consent_prompt(view: ConsentPrompt, audience: str) -> RenderDirective:
    """The reveal gate.

    Exactly two actions. There is no "maybe", no "see who it is first", and no
    "tell me if they said yes" — each of those would be a way round the gate
    rather than a feature.
    """
    return RenderDirective(
        component="consent_prompt",
        audience=audience,
        data=view.model_dump(mode="json"),
        actions=["yes", "no"],
        blocking=True,
    )


def close_out(view: CloseOutView, audience: str) -> RenderDirective:
    """The silent ending.

    No actions. A "why?" button would be a request for exactly the information
    INVARIANT 2 exists to withhold, and a client that offered one would have to
    be told something to put behind it.
    """
    return RenderDirective(
        component="close_out",
        audience=audience,
        data=view.model_dump(mode="json"),
    )


def reveal(view: RevealView, audience: str) -> RenderDirective:
    return RenderDirective(
        component="reveal",
        audience=audience,
        data=view.model_dump(mode="json"),
        actions=["open_conversation"],
    )


def brief(view: LockInBrief, audience: str) -> RenderDirective:
    return RenderDirective(
        component="brief",
        audience=audience,
        data=view.model_dump(mode="json"),
        actions=["message", "not_now"],
    )


def notice(text: str, audience: str) -> RenderDirective:
    """Plain text — a Trust & Safety message, or an actionable error.

    Used for the things a person must be told rather than shown, and kept as
    its own component so a client cannot style a safety message as an
    encounter.
    """
    return RenderDirective(component="notice", audience=audience, data={"text": text})


def directives_for_outcome(
    views: dict[str, RevealView | CloseOutView]
) -> list[RenderDirective]:
    """Turn an encounter's per-user outcome into what each client draws.

    The dispatch is on the view's type, not on a flag: a `CloseOutView` cannot
    be rendered as a reveal because it has no identity to put in one.
    """
    directives: list[RenderDirective] = []
    for audience, view in views.items():
        if isinstance(view, RevealView):
            directives.append(reveal(view, audience))
        else:
            directives.append(close_out(view, audience))
    return directives
