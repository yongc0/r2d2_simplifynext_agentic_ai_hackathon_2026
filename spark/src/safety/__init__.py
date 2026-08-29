"""The parts a model is not allowed to decide.

INVARIANT 6: consent, eligibility and identity-reveal are ordinary Python with
tests. A model must never be the only thing standing between a stranger and
someone's identity — so there is no LLM call anywhere in this package, and
`tests/test_consent.py` asserts that by inspecting the modules' imports.

  `consent.py`     the append-only ledger and the reveal gate
  `guardrails.py`  every user-facing string, checked before it is rendered
  `trust.py`       Trust & Safety: screening, cooldowns, blocks
"""

from src.safety.consent import (
    ConsentLedger,
    RevealRefused,
    build_close_out,
    build_reveal,
    is_mutual_yes,
    reveal_permitted,
)
from src.safety.guardrails import (
    AnonymityLeak,
    GuardrailVerdict,
    IdentityRegistry,
    render,
    screen_outbound,
)
from src.safety.trust import TrustAndSafety

__all__ = [
    "AnonymityLeak",
    "ConsentLedger",
    "GuardrailVerdict",
    "IdentityRegistry",
    "RevealRefused",
    "TrustAndSafety",
    "build_close_out",
    "build_reveal",
    "is_mutual_yes",
    "render",
    "reveal_permitted",
    "screen_outbound",
]
