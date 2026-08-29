"""`spark-profile` — profiles and continuity memory (AgentCore Memory).

`get_profile` returns the matchable profile and never the identity: the `User`
object it reads has `identity` on it, and no field of it appears in the result.

Notes are scoped per owner, expire on a retention window, and can be deleted on
request — the three things §13.4 promises about memory.
"""

from src.mcp._server import run

SERVER_NAME = "spark-profile"

if __name__ == "__main__":
    run(SERVER_NAME)
