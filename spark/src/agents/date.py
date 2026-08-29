"""Date Agent — organisers' classes: **Decision-Support** and **Transaction**.

docs/ARCHITECTURE.md §13.6. Proposes places and activities from shared
interests, once a pair has decided to meet.

Two rules, and the second is the commercially interesting one:

  Ranked on fit first. `spark-venue` scores on tag overlap with the pair's
  shared interests and never sees the partner flag, so a partner venue cannot
  buy its way up the list.

  Commercial partners **are labelled**, always. `DateSuggestion` makes
  `is_commercial_partner` a required field rather than an optional one, so a
  partner venue cannot be rendered without its label — not because we remember
  to set it, but because the model will not construct without it.

Proposing a specific thing at a specific time is the entire point. "We should
meet sometime" is where most of these connections die, and the agent exists to
replace it with something a person can say yes or no to.

`plan()` extends that to three PATHS — a thing to do, and somewhere to eat or
sit afterwards — because a single venue is only slightly easier to accept than
nothing, and because this is the half of the product that is not waiting. The
app finds you one person a day; this is what it does once you have found them.

WHERE THIS AGENT IS ALLOWED TO POINT SOMEWHERE

Invariant 3 forbids rendering a place, and a date plan obviously names places.
The two are reconciled by WHEN and by WHAT:

  WHEN — planning runs on a `LockIn`, which exists only after a mutual reveal.
  Two people who have exchanged names and are choosing where to meet are
  picking a destination together; that is not a disclosure of where either of
  them was.

  WHAT — `suggest_venues` is never given a cell, a coordinate, a distance or
  either person's overlap history. It ranks on shared interests and time of day
  alone. A venue search that accepted a location would quietly become "near
  where you both were", which is exactly the inference the product removed.
  There is no location field on a venue record, so this is structural.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mcp.registry import MCPClient
from src.schemas.agents import DatePath, DatePlan, DateStop, DateSuggestion
from src.schemas.core import LockIn, TimeBucket, User
from src.telemetry.trace import span

AGENT_CLASS = "Decision-Support / Transaction"


@dataclass
class DateAgent:
    client: MCPClient
    name: str = "date"

    def suggest(self, lockin: LockIn, user: User, peer: User) -> DateSuggestion | None:
        """One concrete proposal, or `None` if there is nothing that fits.

        Deterministic ranking over a tool result. There is no model call here:
        the judgement — *whether* to propose — was already made by the
        Continuity Agent, and turning a shared interest and a shared free
        evening into a venue is a lookup, not an opinion.
        """
        if not (
            user.consent_scope.allow_date_suggestions
            and peer.consent_scope.allow_date_suggestions
        ):
            return None

        with span("agent.date", lockin_id=lockin.id) as s:
            shared_interests = sorted(
                set(user.profile.interests) & set(peer.profile.interests)
            )
            shared = self.client.try_call(
                "spark-calendar",
                "shared_availability",
                default={"shared_buckets": []},
                user_a=user.id,
                user_b=peer.id,
            ) or {"shared_buckets": []}
            buckets = shared["shared_buckets"]
            s.set_attribute("shared_interests", len(shared_interests))
            s.set_attribute("shared_buckets", len(buckets))

            if not shared_interests or not buckets:
                # Nothing honest to propose. The Continuity Agent's own message
                # still goes out; it simply does not carry a venue.
                s.set_attribute("outcome", "no proposal — nothing shared to build on")
                return None

            bucket = buckets[0]
            options = self.client.try_call(
                "spark-venue",
                "suggest_venues",
                default={"options": []},
                interests=shared_interests,
                bucket=bucket,
                limit=3,
            ) or {"options": []}
            if not options["options"]:
                s.set_attribute("outcome", "no venue matched; falling back to activity only")
                return None

            best = options["options"][0]
            suggestion = DateSuggestion(
                lockin_id=lockin.id,
                venue_id=best["venue_id"],
                activity=best["activity"],
                rationale=(
                    f"You have both mentioned {' and '.join(shared_interests[:2])}, "
                    f"and you are both usually free in the {bucket.replace('_', ' ')}."
                ),
                fit_score=float(best["fit_score"]),
                is_commercial_partner=bool(best["is_commercial_partner"]),
                proposed_bucket=TimeBucket(bucket),
            )
            s.set_attribute("venue", suggestion.venue_id)
            s.set_attribute("partner", suggestion.is_commercial_partner)
            return suggestion

    @staticmethod
    def render_label(suggestion: DateSuggestion) -> str:
        """How a suggestion reads to a user, partner label included.

        The label is not fine print. If a venue is a commercial partner the
        user is told so in the same sentence as the suggestion.
        """
        label = " (a Spark partner venue)" if suggestion.is_commercial_partner else ""
        return f"{suggestion.activity}{label}. {suggestion.rationale}"

    # -----------------------------------------------------------------
    # Three paths, not one venue
    # -----------------------------------------------------------------

    def plan(self, lockin: LockIn, user: User, peer: User) -> DatePlan:
        """Up to three genuinely different evenings for this pair.

        Deterministic, like `suggest`. Ranking venues by tag overlap and
        pairing an activity with somewhere to eat is a lookup and an ordering,
        not a judgement — and a suggestion that varies run to run is one nobody
        can film twice.

        Returns an empty plan rather than inventing one when the pair has no
        stated common ground or no shared free time. `note` says which, so a
        short list reads as a fact about these two rather than as a failure.
        """
        with span("agent.date.plan", lockin_id=lockin.id) as s:
            if not (
                user.consent_scope.allow_date_suggestions
                and peer.consent_scope.allow_date_suggestions
            ):
                s.set_attribute("outcome", "declined by consent scope")
                return DatePlan(
                    lockin_id=lockin.id,
                    paths=[],
                    note="One of you has turned date suggestions off.",
                )

            shared_interests = sorted(
                set(user.profile.interests) & set(peer.profile.interests)
            )
            shared = self.client.try_call(
                "spark-calendar",
                "shared_availability",
                default={"shared_buckets": []},
                user_a=user.id,
                user_b=peer.id,
            ) or {"shared_buckets": []}
            buckets = shared["shared_buckets"]

            s.set_attribute("shared_interests", len(shared_interests))
            s.set_attribute("shared_buckets", len(buckets))

            if not shared_interests:
                s.set_attribute("outcome", "no shared interests")
                return DatePlan(
                    lockin_id=lockin.id,
                    paths=[],
                    note=(
                        "Nothing you have both mentioned to build on yet. "
                        "Another call may give us something."
                    ),
                )
            if not buckets:
                s.set_attribute("outcome", "no shared availability")
                return DatePlan(
                    lockin_id=lockin.id,
                    paths=[],
                    note="You are not usually free at the same times.",
                )

            # EVERY shared bucket, not just the first. Taking `buckets[0]` and
            # giving up threw away the pair's other free times: two people whose
            # first shared slot happened to be one nothing suits were told there
            # was nothing for them, while an evening they were both free for sat
            # unexamined.
            paths: list[DatePath] = []
            bucket = buckets[0]
            for candidate in buckets:
                leads = self._venues(shared_interests, candidate, "activity", limit=5)
                tables = self._venues(shared_interests, candidate, "food", limit=3)
                tables += self._venues(shared_interests, candidate, "drink", limit=3)
                found = self._compose(lockin, shared_interests, candidate, leads, tables)
                if found:
                    bucket, paths = candidate, found
                    break
            s.set_attribute("bucket", bucket)
            s.set_attribute("paths", len(paths))
            s.set_attribute(
                "partner_paths", sum(1 for p in paths if p.has_commercial_partner)
            )

            note = ""
            if not paths:
                note = (
                    "Nothing open at the time you are both free. We will try "
                    "again when your evenings line up."
                )
            elif len(paths) < 3:
                note = "Only what genuinely fits — we would rather offer fewer."
            return DatePlan(lockin_id=lockin.id, paths=paths, note=note)

    # -----------------------------------------------------------------
    def _venues(
        self, interests: list[str], bucket: str, category: str, limit: int
    ) -> list[dict]:
        result = self.client.try_call(
            "spark-venue",
            "suggest_venues",
            default={"options": []},
            interests=interests,
            bucket=bucket,
            limit=limit,
            category=category,
        ) or {"options": []}
        return list(result["options"])

    def _compose(
        self,
        lockin: LockIn,
        shared_interests: list[str],
        bucket: str,
        leads: list[dict],
        tables: list[dict],
    ) -> list[DatePath]:
        """One path per lead activity, each with somewhere to go afterwards.

        The three must DIFFER: a lead venue is used once, and a table is not
        reused while an unused one fits. Three variations on the same evening
        is a list, not a choice, and the point of offering three is that the
        pair can pick the shape of the night rather than the wording.
        """
        used_tables: set[str] = set()
        paths: list[DatePath] = []

        for lead in leads[:3]:
            table = self._pick_table(lead, tables, used_tables)
            if table is not None:
                used_tables.add(table["venue_id"])

            stops = [self._stop(lead)]
            if table is not None:
                stops.append(self._stop(table))

            # Grounded in what BOTH of them said, read from the venue tags that
            # actually matched. A path that cannot cite anything is not built.
            grounded = sorted(
                {
                    tag
                    for stop_venue in ([lead] + ([table] if table else []))
                    for tag in stop_venue["tags"]
                    if tag in shared_interests
                }
            )
            if not grounded:
                continue

            paths.append(
                DatePath(
                    path_id=f"{lockin.id}-{lead['venue_id']}",
                    lockin_id=lockin.id,
                    headline=self._headline(stops),
                    stops=stops,
                    grounded_in=grounded,
                    rationale=(
                        f"You have both mentioned {_join(grounded[:2])}, and you "
                        f"are both usually free in the {bucket.replace('_', ' ')}."
                    ),
                    fit_score=float(lead["fit_score"]),
                    proposed_bucket=TimeBucket(bucket),
                )
            )
        return paths

    @staticmethod
    def _pick_table(
        lead: dict, tables: list[dict], used: set[str]
    ) -> dict | None:
        """Somewhere to eat or sit after the activity.

        Prefers one not already used by another path, and never the same venue
        as the lead. Returns None rather than repeating: a path with one good
        stop beats a path with a filler second one.
        """
        for table in tables:
            if table["venue_id"] == lead["venue_id"]:
                continue
            if table["venue_id"] in used:
                continue
            return table
        return None

    @staticmethod
    def _stop(venue: dict) -> DateStop:
        return DateStop(
            venue_id=venue["venue_id"],
            activity=venue["activity"],
            category=venue.get("category", "activity"),
            is_commercial_partner=bool(venue["is_commercial_partner"]),
        )

    @staticmethod
    def _headline(stops: list[DateStop]) -> str:
        """Composed from the stops themselves.

        Deliberately not a written title. A generated name would be marketing
        copy about an evening nobody has had yet, and the stops already say
        what it is.
        """
        text = ", then ".join(stop.activity for stop in stops)
        return text[0].upper() + text[1:]

    @staticmethod
    def render_path(path: DatePath) -> str:
        """How a path reads, partner labels included.

        Same rule as `render_label`: if a stop is a commercial partner the
        person is told so beside it, not in fine print somewhere else.
        """
        parts = []
        for stop in path.stops:
            label = " (a Spark partner venue)" if stop.is_commercial_partner else ""
            parts.append(f"{stop.activity}{label}")
        return f"{', then '.join(parts)}. {path.rationale}"


def _join(items: list[str]) -> str:
    """"a and b", or just "a". British spelling, per CLAUDE.md."""
    if len(items) <= 1:
        return items[0] if items else ""
    return " and ".join(items)
