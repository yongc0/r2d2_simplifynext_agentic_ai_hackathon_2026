"""`uv run -m src.api` — serve the API.

Bound to 0.0.0.0 so a phone on the LAN, and later a cloudflared tunnel, reach
the same process. Port 8000, which is what `web/vite.config.ts` proxies /api to.
"""

import uvicorn

from src.config import SETTINGS


def main() -> None:
    print(
        f"Spark API · provider={SETTINGS.model.provider} · "
        f"call={SETTINGS.rules.call_seconds}s"
    )
    if SETTINGS.model.provider == "deterministic":
        print(
            "  No model provider configured; judgement calls use the "
            "deterministic policy."
        )
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
