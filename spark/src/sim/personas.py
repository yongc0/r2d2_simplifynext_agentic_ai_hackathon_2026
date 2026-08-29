"""200 synthetic personas, and the latent traits the system cannot see.

This file decides whether the evaluation means anything, so its generative
story is written down before any result is looked at:

  Each persona has **latent traits** — warmth, curiosity, directness, humour —
  drawn from a distribution. These are what actually determine whether two
  people enjoy three minutes together. **Nothing in Spark can observe them.**

  Each persona also has **stated attributes** — interests, values, personality
  words, availability — which are *noisy indicators* of those latent traits. A
  matcher that reads the stated attributes is therefore reading a corrupted
  signal, which is the honest model of what a dating app actually has.

  `latent_affinity(a, b)` combines the latent traits and is used only by
  `src/sim/responder.py` to decide what the simulated humans do. No agent, no
  arm, and no metric may read it.

Why this shape. Joel, Eastwick & Finkel (2017) found that machine learning over
100+ self-reported traits could not predict relationship-specific attraction
above chance. If our simulator let stated attributes determine the outcome, the
Match Agent would "win" by construction and the result would be worthless. The
noise term is what keeps the comparison in `eval/run_arms.py` capable of
returning a negative result — which CLAUDE.md pre-registers us to report.

Everything here is fictional. No real personal data, following the lab repo's
convention.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

from src.config import DATA_DIR
from src.ids import handle_for_index
from src.schemas.core import (
    ConsentScope,
    Intent,
    PrivateIdentity,
    Profile,
    TimeBucket,
    User,
    VerificationTier,
)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Invented surnames and given names. Chosen so that no name is also an
#: ordinary English word — the anonymity scanner matches names on word
#: boundaries, and a persona called "Grace" would make every polite sentence
#: look like a leak.
_GIVEN_NAMES = (
    "Ardith", "Belen", "Caius", "Delwyn", "Elowen", "Fenwick", "Gervase",
    "Hestia", "Ilario", "Jorunn", "Kestrel", "Lorcan", "Merrick", "Nerissa",
    "Orlaith", "Perrin", "Quilla", "Rhodri", "Sabra", "Torin", "Ulric",
    "Verity", "Wynne", "Xanthe", "Yorick", "Zenobia",
)
_FAMILY_NAMES = (
    "Anselm", "Brackley", "Corvino", "Danforth", "Eastcote", "Fairlie",
    "Gowrie", "Halloway", "Iselin", "Jerrold", "Kilbride", "Lambourne",
    "Marchetti", "Northway", "Ollivant", "Pemberton", "Quillon", "Ravensby",
    "Stellenbosch", "Thornbury", "Ulverston", "Vandermeer", "Wexford",
)

_INTERESTS = (
    "climbing", "running", "cooking", "film", "live music", "board games",
    "cycling", "photography", "reading", "hiking", "coffee", "pottery",
    "swimming", "languages", "volunteering", "gardening", "chess", "baking",
    "football", "yoga", "birdwatching", "woodwork",
)
_VALUES = (
    "honesty", "ambition", "family", "independence", "humour", "stability",
    "adventure", "kindness", "curiosity", "faith",
)
_PERSONALITY_WORDS = (
    "quiet", "warm", "dry", "direct", "playful", "measured", "earnest",
    "restless", "steady", "wry",
)
_LIFESTYLES = (
    "works late most weekdays",
    "up early, in bed by ten",
    "shift work, irregular weeks",
    "office hours, free evenings",
    "studying part-time alongside work",
    "travels for work every few weeks",
)
_LANGUAGES = ("English", "Mandarin", "Malay", "Tamil", "Cantonese", "Hokkien")
_AGE_BANDS = ("18-24", "25-34", "35-44", "45-54", "55+")

#: The four latent traits. Named so the responder reads legibly; the values
#: never leave `src/sim/`.
_LATENT_TRAITS = ("warmth", "curiosity", "directness", "humour")


@dataclass
class Persona:
    """A simulated person: what Spark can see, and what it cannot.

    `latent` is the private half. `src/sim/responder.py` is the only module
    that reads it, and `eval/run_arms.py` asserts that no arm has access to it.
    """

    user: User
    latent: dict[str, float]
    #: How readily this person accepts a call at all, independent of who it is
    #: with. Some people are simply busier or more hesitant, and a matcher
    #: cannot fix that.
    openness: float
    #: How reliably their stated attributes reflect their latent traits. Low
    #: values are people who describe themselves badly — the reason a profile
    #: is a corrupted signal rather than a clean one.
    self_report_fidelity: float
    #: Home cells, which drive whose paths cross. Never rendered.
    home_cells: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.user.id


def latent_affinity(a: Persona, b: Persona) -> float:
    """How much these two would actually enjoy three minutes, in [0, 1].

    Unobservable by construction. Complementarity on directness (one person
    leading a three-minute conversation helps), similarity on warmth and
    humour, and a shared-curiosity bonus. The exact functional form is a
    modelling choice, not a claim about people — what matters for the
    evaluation is only that it depends on variables no agent can read.
    """
    warmth = 1.0 - abs(a.latent["warmth"] - b.latent["warmth"])
    humour = 1.0 - abs(a.latent["humour"] - b.latent["humour"])
    directness = abs(a.latent["directness"] - b.latent["directness"])   # complementary
    curiosity = (a.latent["curiosity"] + b.latent["curiosity"]) / 2
    raw = 0.32 * warmth + 0.24 * humour + 0.18 * directness + 0.26 * curiosity
    return max(0.0, min(1.0, raw))


def generate_personas(count: int, seed: int) -> list[Persona]:
    """Deterministic from `seed`. Same seed, same 200 people, every run."""
    rng = random.Random(seed)
    personas: list[Persona] = []
    for index in range(count):
        personas.append(_make_persona(index, rng))
    return personas


def _make_persona(index: int, rng: random.Random) -> Persona:
    user_id = f"u{index:03d}"
    latent = {trait: rng.betavariate(2.2, 2.2) for trait in _LATENT_TRAITS}
    fidelity = 0.35 + 0.5 * rng.random()

    # Stated attributes are drawn *from* the latent traits, then corrupted by
    # (1 - fidelity). This is the whole point: a matcher reading the profile is
    # reading the latent traits through noise, never directly.
    curiosity_signal = _blend(latent["curiosity"], rng.random(), fidelity)
    warmth_signal = _blend(latent["warmth"], rng.random(), fidelity)

    interest_count = 3 + int(curiosity_signal * 4)
    interests = _draw_tastes(
        _INTERESTS, _INTEREST_TASTES, latent, fidelity,
        k=min(interest_count, len(_INTERESTS)), rng=rng,
    )
    values = _draw_tastes(
        _VALUES, _VALUE_TASTES, latent, fidelity,
        k=2 + int(warmth_signal * 2), rng=rng,
    )
    personality = " ".join(rng.sample(_PERSONALITY_WORDS, k=2))

    intents = _draw_intents(rng)
    buckets = _draw_availability(rng)
    languages = ["English"] + rng.sample(_LANGUAGES[1:], k=rng.choice([0, 0, 1, 1, 2]))

    identity = PrivateIdentity(
        display_name=f"{_GIVEN_NAMES[index % len(_GIVEN_NAMES)]} "
                     f"{_FAMILY_NAMES[(index // len(_GIVEN_NAMES) + index) % len(_FAMILY_NAMES)]}",
        phone=f"+65{80000000 + index}",
        email=f"persona{index:03d}@example.invalid",     # RFC 2606 reserved TLD
    )
    profile = Profile(
        user_id=user_id,
        intents=intents,
        interests=interests,
        values=values,
        personality=personality,
        lifestyle=rng.choice(_LIFESTYLES),
        languages=sorted(set(languages)),
        availability_window=buckets,
        dealbreakers=(["smoking"] if rng.random() < 0.2 else []),
        age_band=rng.choice(_AGE_BANDS),
    )
    # What the user has permitted to be used for matching. Most people permit
    # most things; a minority withhold, and the Match Agent must respect it.
    matchable = ["intents", "languages", "availability_window", "age_band"]
    if rng.random() < 0.85:
        matchable.append("interests")
    if rng.random() < 0.7:
        matchable.append("values")
    if rng.random() < 0.6:
        matchable.append("personality")

    consent_scope = ConsentScope(
        user_id=user_id,
        matchable_fields=matchable,
        allow_continuity_notes=rng.random() < 0.95,
        allow_conversation_prompts=rng.random() < 0.45,     # opt-in, so a minority
        allow_date_suggestions=rng.random() < 0.9,
    )
    user = User(
        id=user_id,
        identity=identity,
        profile=profile,
        consent_scope=consent_scope,
        verification_tier=_draw_tier(rng),
        handle=handle_for_index(index),
    )
    return Persona(
        user=user,
        latent=latent,
        openness=0.35 + 0.55 * rng.random(),
        self_report_fidelity=fidelity,
        # Two DISTINCT cells. Drawn with `sample` rather than twice with
        # `randrange`, which could hand someone the same cell twice and put
        # them in a cell-bucket list twice over.
        home_cells=tuple(f"cell-{n:02d}" for n in rng.sample(range(40), k=2)),
    )


def _blend(signal: float, noise: float, fidelity: float) -> float:
    return fidelity * signal + (1 - fidelity) * noise


def _taste_vectors(items: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Give every interest and value a fixed position in latent-trait space.

    Deterministic from the item's name, so the mapping is stable across runs and
    across seeds — it is a property of the world, not of a particular draw.
    """
    vectors: dict[str, dict[str, float]] = {}
    for item in items:
        digest = hashlib.sha256(item.encode()).digest()
        vectors[item] = {
            trait: digest[i] / 255 for i, trait in enumerate(_LATENT_TRAITS)
        }
    return vectors


_INTEREST_TASTES = _taste_vectors(_INTERESTS)
_VALUE_TASTES = _taste_vectors(_VALUES)


def _draw_tastes(
    items: tuple[str, ...],
    tastes: dict[str, dict[str, float]],
    latent: dict[str, float],
    fidelity: float,
    k: int,
    rng: random.Random,
) -> list[str]:
    """Draw `k` items, weighted towards ones that suit this person's traits.

    This is what makes the docstring at the top of the file true. Without it,
    interests were drawn uniformly, so two people sharing "climbing" said
    nothing whatsoever about their latent affinity — and the Match Agent could
    not have beaten random assignment however good it was. A pre-registered
    comparison that can only come out one way is not a test, so the signal has
    to be genuinely present.

    It also has to be genuinely weak. `fidelity` is the share of the weighting
    that comes from the person's traits at all; the rest is noise, and the
    resulting correlation between a shared interest and a good conversation is
    small. That is the finding the whole simulator is built around: stated
    traits carry *something*, and nowhere near enough to predict attraction
    (Joel, Eastwick & Finkel, 2017).
    """
    weights = []
    for item in items:
        vector = tastes[item]
        # Closeness of this item's position to the person's traits, in [0, 1].
        distance = sum(abs(vector[t] - latent[t]) for t in _LATENT_TRAITS) / len(
            _LATENT_TRAITS
        )
        affinity = 1.0 - distance
        weights.append(max(0.05, _blend(affinity, rng.random(), fidelity)))

    chosen: list[str] = []
    pool = list(items)
    pool_weights = list(weights)
    for _ in range(min(k, len(pool))):
        pick = rng.choices(range(len(pool)), weights=pool_weights, k=1)[0]
        chosen.append(pool.pop(pick))
        pool_weights.pop(pick)
    return chosen


def _draw_intents(rng: random.Random) -> list[Intent]:
    """Most people name one thing. A minority name two.

    Never zero: a persona with no stated intent could not be matched at all,
    and §13.1 forbids inferring one. That case is real, and it is handled by
    the Onboarding Agent asking — not by the generator inventing a persona the
    simulation could never serve.
    """
    roll = rng.random()
    if roll < 0.45:
        primary = [Intent.PARTNER_LONG_TERM]
    elif roll < 0.72:
        primary = [Intent.FRIENDS]
    else:
        primary = [Intent.PARTNER_SHORT_TERM]
    if rng.random() < 0.18:
        extra = rng.choice([i for i in Intent if i not in primary])
        primary.append(extra)
    return primary


def _draw_availability(rng: random.Random) -> list[TimeBucket]:
    buckets = [b for b in TimeBucket if rng.random() < 0.4]
    if not buckets:
        buckets = [TimeBucket.EVENING]      # everyone is free sometime
    return buckets


def _draw_tier(rng: random.Random) -> VerificationTier:
    roll = rng.random()
    if roll < 0.15:
        return VerificationTier.UNVERIFIED
    if roll < 0.75:
        return VerificationTier.PHONE
    return VerificationTier.GOVERNMENT_ID


# ---------------------------------------------------------------------------
# Persistence — so `data/personas.json` is inspectable
# ---------------------------------------------------------------------------


def write_personas(personas: list[Persona], path: Path | None = None) -> Path:
    """Write the cohort to `data/personas.json`.

    Includes the latent traits, deliberately: the file is documentation of how
    the simulation works, and hiding the ground truth in a repository whose
    evaluation depends on it would be the wrong kind of tidy. Nothing at
    runtime reads the latent block except `src/sim/responder.py`.
    """
    path = path or (DATA_DIR / "personas.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": (
            "Synthetic personas. No real personal data. 'latent' is ground "
            "truth for the simulated humans and is not observable by any agent "
            "or evaluation arm."
        ),
        "count": len(personas),
        "personas": [
            {
                "user": p.user.model_dump(mode="json"),
                "latent": p.latent,
                "openness": p.openness,
                "self_report_fidelity": p.self_report_fidelity,
                "home_cells": list(p.home_cells),
            }
            for p in personas
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
