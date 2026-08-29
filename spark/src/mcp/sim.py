"""`spark-sim` — the simulated world.

Personas, their overlaps, and the state the evaluation arms run against.
Everything it serves is synthetic: fictional people, fictional routines. There
is no real personal data anywhere in this repository.
"""

from src.mcp._server import run

SERVER_NAME = "spark-sim"

if __name__ == "__main__":
    run(SERVER_NAME)
