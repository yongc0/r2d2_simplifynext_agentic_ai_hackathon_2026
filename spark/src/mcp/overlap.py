"""`spark-overlap` — coarse cell + time bucket, historical only.

The tool bodies are in `services.py`; this module publishes them over MCP.

What is NOT here matters more than what is. There is no `who_is_near_me`, no
`live_position`, no `distance_between`. Live proximity was removed from the
design deliberately (docs/ARCHITECTURE.md §13.3, proposal §3.2) because it is a
de-anonymisation and stalking vector, and the absence is enforced by this file
being the only place overlap data leaves the store.
"""

from src.mcp._server import run

SERVER_NAME = "spark-overlap"

if __name__ == "__main__":
    run(SERVER_NAME)
