"""Every user-facing string, checked before anyone sees it.

INVARIANT 3 lives here: no distance, place name, coordinate or map position is
ever rendered to a user. So does the enforcement half of INVARIANT 1 — an
identity token belonging to someone other than the viewer must not appear in
any output before that pair has mutually revealed.

The design point: there is exactly one function, `render()`, that turns a
string into something a user sees. Everything user-facing in Spark goes through
it. That makes the anonymity leakage rate (§18) a real measurement rather than
an assertion — it is the share of rendered strings that this scanner rejected,
counted over every string the simulation produced.

On strictness. `SETTINGS.strict_guardrails` is on in every run we ship, and a
violation raises. Silently redacting would be the friendlier engineering choice
and the wrong product choice: a leak that is quietly patched over is a leak
nobody fixes. Bedrock Guardrails sits in this position in the deployed design
(§16); the pattern set below is the local stand-in, and failures are logged,
never silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config import SETTINGS
from src.schemas.core import User
from src.telemetry.metrics import METRICS


class AnonymityLeak(Exception):
    """A string that would have identified someone, or placed them."""


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

#: Anything that states or implies where a person is or was. INVARIANT 3.
#: Written out one per line so that adding a case is a one-line diff and a
#: reviewer can see exactly what is forbidden.
_LOCATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b\d+(?:\.\d+)?\s*(?:m|km|metres?|meters?|kilometres?|kilometers?|miles?|mi)\b",
     "states a distance"),
    (r"\b\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b", "contains coordinates"),
    (r"\b(?:lat|latitude|lon|lng|longitude)\b", "names a coordinate field"),
    (r"\bnear(?:by|\s+you|\s+your)\b", "implies proximity"),
    (r"\b(?:just )?around the corner\b", "implies proximity"),
    (r"\bwalking distance\b", "implies proximity"),
    (r"\b\d+\s*(?:min(?:ute)?s?)\s+(?:away|from you)\b", "states a travel time"),
    (r"\bsame (?:building|block|street|office|floor|mrt|station)\b", "names a place"),
    (r"\bright now (?:at|in|near)\b", "implies live location"),
    (r"\bcurrently (?:at|in|near)\b", "implies live location"),
    (r"\bcell[_ ]?id\b", "exposes the overlap cell"),
)

#: Trust & Safety categories (§13.8). Deterministic patterns; no model decides
#: whether something is harassment, because a model that is wrong 1% of the
#: time is wrong about a person's safety 1% of the time.
_HARM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:kill|hurt|beat|find)\s+(?:you|u)\b", "threat"),
    (r"\byou(?:'| a)?re\s+(?:ugly|worthless|disgusting|pathetic)\b", "harassment"),
    (r"\b(?:shut up|stupid bitch|slut|whore)\b", "harassment"),
    (r"\b(?:nudes?|sext|send pics|naked)\b", "sexual_content"),
    (r"\bstop ignoring me\b", "harassment"),
    (r"\b(?:send|transfer|wire)\s+(?:me\s+)?(?:\$|sgd|usd)?\s?\d", "scam"),
    (r"\bverify your account\b.{0,40}\blink\b", "scam"),
)

#: Rules where two things must BOTH appear, in any order.
#:
#: Added because the seeded adversarial set caught a false negative: an
#: order-dependent pattern matched "crypto ... guaranteed returns" but not
#: "guaranteed returns on crypto", which is the same message written the
#: obvious other way round. Word order is not a safety property, and a filter
#: that can be defeated by rearranging a sentence is not a filter.
_HARM_COOCCURRENCE: tuple[tuple[str, str, str], ...] = (
    (
        r"\b(?:invest|investment|crypto|bitcoin|usdt|forex|trading)\b",
        r"\b(?:guarantee|guaranteed|profits?|returns?|roi|double your)\b",
        "scam",
    ),
    (
        r"\b(?:gift ?card|itunes|steam card|top ?up)\b",
        r"\b(?:send|buy|urgent|help me)\b",
        "scam",
    ),
)

#: Attempts to route around the consent gate — asking for contact details
#: before a mutual reveal. Screened separately because the response differs:
#: this is usually a person who does not know the rules, not a bad actor.
_CIRCUMVENTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:whats\s?app|telegram|insta(?:gram)?|snap(?:chat)?|wechat)\b",
     "consent_circumvention"),
    (r"\bwhat(?:'s| is) your (?:real )?(?:name|number|handle)\b",
     "consent_circumvention"),
    (r"\b(?:\+65\s?)?\d{4}\s?\d{4}\b", "contact_exfiltration"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "contact_exfiltration"),
)

_COMPILED_LOCATION = tuple((re.compile(p, re.I), why) for p, why in _LOCATION_PATTERNS)
_COMPILED_HARM = tuple((re.compile(p, re.I), why) for p, why in _HARM_PATTERNS)
_COMPILED_CIRCUMVENTION = tuple(
    (re.compile(p, re.I), why) for p, why in _CIRCUMVENTION_PATTERNS
)
_COMPILED_COOCCURRENCE = tuple(
    (re.compile(a, re.I), re.compile(b, re.I), why)
    for a, b, why in _HARM_COOCCURRENCE
)


# ---------------------------------------------------------------------------
# Identity registry
# ---------------------------------------------------------------------------


@dataclass
class IdentityRegistry:
    """Who the identifying strings belong to.

    The scanner needs to know that "Marcus" is a person's name and not a word,
    so it is told, once, at registration. Place names live here too: the
    simulator knows what its cells are called and the registry is how that
    knowledge is used to *forbid* the names rather than to render them.
    """

    #: user_id -> the strings that identify them
    _tokens: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: place names that exist in the simulator and must never be rendered
    _place_names: set[str] = field(default_factory=set)
    #: frozenset({a, b}) for every pair that has mutually revealed
    _revealed_pairs: set[frozenset[str]] = field(default_factory=set)

    def register(self, user: User) -> None:
        self._tokens[user.id] = user.identity.tokens()

    def register_places(self, names: list[str]) -> None:
        self._place_names.update(n.lower() for n in names if n)

    def mark_revealed(self, user_a: str, user_b: str) -> None:
        """Called only after `consent.build_reveal` has succeeded. From this
        point the pair may see each other's names — and only each other's."""
        self._revealed_pairs.add(frozenset({user_a, user_b}))

    def is_revealed(self, user_a: str, user_b: str) -> bool:
        return frozenset({user_a, user_b}) in self._revealed_pairs

    def tokens_for(self, user_id: str) -> tuple[str, ...]:
        return self._tokens.get(user_id, ())

    def others(self, viewer_id: str) -> list[str]:
        return [u for u in self._tokens if u != viewer_id]

    def place_names(self) -> set[str]:
        return set(self._place_names)

    def reset(self) -> None:
        self._tokens.clear()
        self._place_names.clear()
        self._revealed_pairs.clear()


#: Process-wide, because the guardrail must see every user the simulation made,
#: not just the two in the current encounter.
IDENTITIES = IdentityRegistry()


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


@dataclass
class GuardrailVerdict:
    """Why a string was refused, in language an operator can act on."""

    allowed: bool
    violations: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    def reason(self) -> str:
        return "; ".join(self.violations)


#: A token made only of letters, digits and spaces is a name or a place, and is
#: matched on word boundaries. Anything else — an email, a phone number — is
#: matched as a substring, because its own punctuation *is* its boundary.
_PLAIN_TOKEN = re.compile(r"^[a-z0-9 ]+$")
_DIGITS = re.compile(r"\D+")


def _word_present(needle: str, haystack_lower: str) -> bool:
    """Case-insensitive match for one identity or place token.

    Two matching modes, and the distinction matters in both directions:

      names and places  matched on word boundaries, so a persona called "Ana"
                        does not trip on "analysis" — a guardrail that cries
                        wolf is a guardrail somebody switches off.
      emails and phones matched as substrings, and phone numbers additionally
                        compared digits-only, so "+65 9123 4567" is caught when
                        the stored form is "+6591234567". Formatting is not a
                        way round an anonymity check.
    """
    needle = needle.lower().strip()
    if not needle:
        return False
    if _PLAIN_TOKEN.match(needle):
        # \b on both ends: matches "raffles place." and "(marcus)" alike, which
        # the previous character-class lookaround did not.
        return re.search(rf"\b{re.escape(needle)}\b", haystack_lower) is not None
    if needle in haystack_lower:
        return True
    digits = _DIGITS.sub("", needle)
    if len(digits) >= 7:
        return digits in _DIGITS.sub("", haystack_lower)
    return False


def screen_outbound(
    text: str,
    viewer_id: str,
    *,
    registry: IdentityRegistry | None = None,
    subject_id: str | None = None,
) -> GuardrailVerdict:
    """Check a string that is about to be shown to `viewer_id`.

    `subject_id`, when given, is the other party in the current encounter. If
    that pair has mutually revealed, their name is allowed through — that is
    what the reveal *is*. Every other user's identity is forbidden regardless.
    """
    registry = registry or IDENTITIES
    lowered = text.lower()
    violations: list[str] = []
    categories: list[str] = []

    # --- INVARIANT 3: place, distance, coordinate ---------------------
    for pattern, why in _COMPILED_LOCATION:
        if pattern.search(text):
            violations.append(f"{why}: {pattern.pattern}")
            categories.append("location")
    for place in registry.place_names():
        if _word_present(place, lowered):
            violations.append(f"names the place {place!r}")
            categories.append("location")

    # --- INVARIANT 1: identity of anyone the viewer has not revealed with
    for other_id in registry.others(viewer_id):
        if subject_id == other_id and registry.is_revealed(viewer_id, other_id):
            continue                    # a mutual reveal — this is the point
        for token in registry.tokens_for(other_id):
            if _word_present(token, lowered):
                violations.append(
                    f"contains an identifier belonging to {other_id} before a mutual reveal"
                )
                categories.append("identity")
                break

    return GuardrailVerdict(
        allowed=not violations,
        violations=violations,
        categories=sorted(set(categories)),
    )


def screen_inbound(text: str) -> GuardrailVerdict:
    """Check something a *user* wrote, for harm and for consent circumvention.

    Used by Trust & Safety on onboarding text and post-reveal messages (§13.8).
    Kept separate from `screen_outbound` because the two ask different
    questions: outbound asks "would this leak", inbound asks "is this harmful".
    """
    violations: list[str] = []
    categories: list[str] = []
    for pattern, category in _COMPILED_HARM + _COMPILED_CIRCUMVENTION:
        if pattern.search(text):
            violations.append(f"matched {category} pattern")
            categories.append(category)
    for first, second, category in _COMPILED_COOCCURRENCE:
        if first.search(text) and second.search(text):
            violations.append(f"matched {category} pattern (co-occurrence)")
            categories.append(category)
    return GuardrailVerdict(
        allowed=not violations,
        violations=violations,
        categories=sorted(set(categories)),
    )


def render(
    text: str,
    viewer_id: str,
    *,
    registry: IdentityRegistry | None = None,
    subject_id: str | None = None,
    context: str = "",
) -> str:
    """The single exit from the system to a person.

    Records the anonymity check either way — a run where nothing was rendered
    and a run where nothing leaked must not look the same in the report.
    """
    verdict = screen_outbound(text, viewer_id, registry=registry, subject_id=subject_id)
    METRICS.record_anonymity_check(
        leaked=not verdict.allowed,
        detail=f"{context or 'render'}: {verdict.reason()}" if not verdict.allowed else "",
    )
    if verdict.allowed:
        return text
    message = (
        f"refusing to render text to {viewer_id}"
        f"{f' in {context}' if context else ''}: {verdict.reason()}. "
        "Fix the agent that produced this string; do not relax the guardrail."
    )
    if SETTINGS.strict_guardrails:
        raise AnonymityLeak(message)
    return "[withheld]"
