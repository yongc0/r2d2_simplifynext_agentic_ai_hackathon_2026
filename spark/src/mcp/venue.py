"""`spark-venue` — date options, once a pair has decided to meet.

Ranked on fit with the pair's shared interests. §13.6: commercial partners may
only appear where they already rank, and are labelled. The ranking function
does not receive the partner flag, so it cannot be influenced by it.
"""

from src.mcp._server import run

SERVER_NAME = "spark-venue"

if __name__ == "__main__":
    run(SERVER_NAME)
