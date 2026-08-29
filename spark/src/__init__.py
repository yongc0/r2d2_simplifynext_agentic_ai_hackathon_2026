"""Spark — one anonymous three-minute voice call a day.

Read `docs/ARCHITECTURE.md` for the design. The short version:

    onboarding -> daily overlap match -> anonymous encounter -> 3-minute call
                -> mutual reveal -> lock-in with continuity over weeks

Everything here is simulated. No real users, no real telephony, no real
location data, no real personal data of any kind.
"""

__version__ = "0.1.0"
