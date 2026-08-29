"""Pydantic models — the contract at every agent boundary.

CLAUDE.md: *no bare dicts crossing an agent boundary.* Schema validation pass
rate is one of the six graded metrics, and it is only measurable because these
exist.

Three files, three different jobs:

  `core.py`    the durable domain — User, Overlap, Encounter, Consent, LockIn.
               What the system stores.
  `agents.py`  what each agent must emit. One model per agent output.
  `views.py`   the ONLY shapes a user is ever shown. Anything a person can see
               is constructed here, which is what makes the anonymity
               invariants enforceable in one place instead of everywhere.
"""

from src.schemas.agents import (
    ContinuityAction,
    ContinuityDraft,
    ConversationDraft,
    ConversationPrompt,
    DateSuggestion,
    GuardianPlan,
    MatchChoice,
    MatchDecision,
    OnboardingExtraction,
    SafetyVerdict,
)
from src.schemas.core import (
    Consent,
    ConsentDecision,
    ConsentScope,
    ContinuityNote,
    Encounter,
    EncounterState,
    Intent,
    LockIn,
    LockInState,
    Outcome,
    Overlap,
    Profile,
    TimeBucket,
    User,
    VerificationTier,
)
from src.schemas.views import (
    AnonymousPeer,
    CloseOutView,
    ConsentPrompt,
    EncounterCard,
    LockInBrief,
    RevealView,
)

__all__ = [
    "AnonymousPeer",
    "CloseOutView",
    "Consent",
    "ConsentDecision",
    "ConsentPrompt",
    "ConsentScope",
    "ContinuityAction",
    "ContinuityDraft",
    "ConversationDraft",
    "ContinuityNote",
    "ConversationPrompt",
    "DateSuggestion",
    "Encounter",
    "EncounterCard",
    "EncounterState",
    "GuardianPlan",
    "Intent",
    "LockIn",
    "LockInBrief",
    "LockInState",
    "MatchChoice",
    "MatchDecision",
    "OnboardingExtraction",
    "Outcome",
    "Overlap",
    "Profile",
    "RevealView",
    "SafetyVerdict",
    "TimeBucket",
    "User",
    "VerificationTier",
]
