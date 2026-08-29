"""The LangGraph supervisor, the state machine, and the consent interrupt.

Start at `supervisor.py`: its module docstring is the architecture slide, and
the graph it compiles is the diagram. `nodes.py` holds one node per transition
in docs/ARCHITECTURE.md 14, and `state.py` holds what travels between them.

The consent gate is an `interrupt()` in `nodes.py`, in two places: before the
call, and after it. There is no code path past either without a resume
carrying both answers.
"""
