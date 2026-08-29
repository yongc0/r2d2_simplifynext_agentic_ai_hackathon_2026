"""`spark-voice` — the anonymous bridge. Mock, as the MVP scope requires.

INVARIANT 4 lives in `services.connect_call`: every call stops at 180 seconds,
the duration is read from config, and there is no argument that extends it.

Both legs are anonymous tokens. There is no telephone number on either side of
this bridge, so there is nothing here to leak even by accident — which is the
point of putting the bridge behind a tool boundary in the first place.
"""

from src.mcp._server import run

SERVER_NAME = "spark-voice"

if __name__ == "__main__":
    run(SERVER_NAME)
