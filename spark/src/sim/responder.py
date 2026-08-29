"""What the simulated humans do.

The other half of the evaluation's honesty. Three decisions, in the order a
real encounter meets them:

  accept the call     driven by openness and availability — things a matcher
                      can partly see, and partly cannot.
  say yes afterwards  driven by `latent_affinity`, which no agent can observe,
                      plus a large unexplained term. This is the decision that
                      decides whether the Match Agent is worth anything.
  keep the lock-in    driven by affinity and by pace fit, over weeks.

The unexplained term is not a hedge; it is the finding. Joel, Eastwick & Finkel
(2017) could not predict relationship-specific attraction above chance from
100+ self-reported traits. A simulator without a large irreducible component
would be modelling a world where that result is false, and every conclusion
drawn from it would be about the simulator rather than about Spark.

Every draw is from a seeded RNG owned by the caller, so a six-week run is
reproducible from one integer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.sim.personas import Persona, latent_affinity

#: How much of the post-call decision is affinity, and how much is everything
#: else — mood, timing, the thing they said at second forty. Set once, before
#: any result was looked at, and not adjusted afterwards.
_AFFINITY_WEIGHT = 0.55
_BASE_YES_RATE = 0.30


@dataclass
class Responder:
    """Simulated human behaviour. Reads latent traits; nothing else may."""

    rng: random.Random

    # -- pre-call -------------------------------------------------------
    def accepts_call(self, person: Persona, bucket_matches: bool, day_index: int) -> bool:
        """Will this person take today's call?

        Availability is the dominant term, then openness, then a mild novelty
        decay — people answer fewer notifications in week six than in week one,
        which is exactly the effect a retention claim has to survive.
        """
        probability = person.openness * (0.85 if bucket_matches else 0.35)
        probability *= 1.0 - min(0.25, 0.006 * day_index)
        return self.rng.random() < probability

    # -- post-call ------------------------------------------------------
    def says_yes(self, person: Persona, other: Persona) -> bool:
        """The reveal decision, made privately after three minutes.

        Deliberately *not* symmetric: each person draws separately, so a mutual
        yes needs two independent decisions to land — which is why the mutual
        connect rate is so much lower than the individual yes rate, in the
        simulation and in life.
        """
        affinity = latent_affinity(person, other)
        probability = _BASE_YES_RATE + _AFFINITY_WEIGHT * (affinity - 0.5)
        probability = max(0.02, min(0.95, probability))
        return self.rng.random() < probability

    # -- over weeks -----------------------------------------------------
    def replies_this_week(self, person: Persona, other: Persona, week: int, pace_fit: float) -> bool:
        """Does the lock-in stay alive this week?

        `pace_fit` in [0, 1] is how well the system has learned this pair's
        rhythm. It is the one lever the Continuity Agent actually has, and it is
        deliberately a modest one — a good brief helps, and it does not make two
        people who did not click keep talking.
        """
        affinity = latent_affinity(person, other)
        base = 0.35 + 0.45 * affinity
        base *= 0.80 + 0.20 * pace_fit
        base *= 1.0 - min(0.30, 0.05 * week)        # attention decays with time
        return self.rng.random() < base

    def meets_in_person(self, person: Persona, other: Persona, contacts: int, proposed: bool) -> bool:
        """Whether a lock-in turns into a real meeting.

        A concrete proposal matters a great deal here, which is the Date
        Agent's entire justification: "we should meet sometime" is where most
        of these die.

        These coefficients are a stated prior, not a measurement, and they are
        deliberately pessimistic: this check runs once per week per lock-in, so
        a generous per-check rate compounds into an implausible fortnight. They
        were set before any arm was run and apply identically to all three.
        """
        affinity = latent_affinity(person, other)
        probability = 0.02 + 0.10 * affinity + 0.015 * min(contacts, 5)
        if proposed:
            probability *= 1.6
        return self.rng.random() < min(0.6, probability)
