"""The simulator: personas, routines, and simulated human behaviour.

Kept apart from `src/agents/` on purpose. Nothing in the agent layer may import
from here — the simulator holds the latent ground truth that decides what the
simulated humans do, and an agent that could read it would be cheating at its
own evaluation.
"""
