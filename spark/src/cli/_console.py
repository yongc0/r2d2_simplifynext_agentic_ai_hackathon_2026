"""Console setup shared by both entry points.

Windows terminals still default to a legacy code page, and the product's copy
is full of em dashes and British punctuation. Without this, a demo recorded on
Windows shows mojibake in every line of the trace — which is a silly reason for
a submission video to look broken.
"""

from __future__ import annotations

import sys


def use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A redirected or otherwise unusual stream. Not worth failing a
                # run over — the output is merely less pretty.
                pass


def rule(title: str = "", char: str = "=", width: int = 78) -> str:
    if not title:
        return char * width
    return f"\n{char * width}\n{title}\n{char * width}"
