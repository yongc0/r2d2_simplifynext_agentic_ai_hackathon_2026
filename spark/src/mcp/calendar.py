"""`spark-calendar` — availability.

Coarse buckets, never timestamps. A bucket says *when* two people could talk; a
timestamp plus an overlap cell would say a great deal about where they were.
"""

from src.mcp._server import run

SERVER_NAME = "spark-calendar"

if __name__ == "__main__":
    run(SERVER_NAME)
