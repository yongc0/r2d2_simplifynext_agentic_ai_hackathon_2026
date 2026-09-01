"""Durable Date Studio memory.

The product claims Spark gets better at planning for you. That claim is only
true if what it learned is still there tomorrow, so this is a SQLite table and
not a dictionary on `SparkSession` — which is exactly what the consent ledger
and the lock-in store still are, and why both are listed as pilot blockers.

WHAT THIS IS AND IS NOT

It is a preference store that a deterministic scorer re-ranks from. Improvement
comes from rows you can read, correct and delete.

It is NOT training. Nothing here updates a model's weights, and no
documentation, span or piece of interface copy may imply that it does. The
distinction matters to a judge and it matters more to a user: a preference you
can inspect and delete is a different kind of thing from a model that has
absorbed you.

WHY THE INTERFACE IS THIS NARROW

`DateMemoryStore` is a handful of methods over rows keyed by owner and scope,
because the intended replacement is AgentCore Memory. That is a target, not a
completed integration — nothing in this repository talks to it today, and the
documentation says so in those words.

SCOPE IS A SAFETY BOUNDARY, NOT A FILTER

A `lockin` item must never reach a different lock-in. Someone's private reaction
to one person is not a fact about them in general, and letting it drift would
leak the shape of that reaction into an unrelated plan. Every read takes the
scope it is allowed to see, and `tests/test_date_studio.py` holds the line.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from src.schemas.date_studio import (
    CONFIDENCE_STEP,
    EXPLICIT_CONFIDENCE,
    MAX_INFERRED_CONFIDENCE,
    DateMemoryItem,
    DatePlanFeedback,
    DatePlanRecord,
)

_MEMORY_TABLE = "date_memory"
_PLAN_TABLE = "date_plan"
_FEEDBACK_TABLE = "date_feedback"


class DateMemoryStore:
    """Rows on disk, in the same database as the graph checkpoints.

    Same file on purpose: the memory and the encounters it is about should be
    deleted together. A stale preference store pointing at encounters that no
    longer exist is a worse state than no store at all.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        # SQLite connections are not safe to share across threads without care,
        # and the API is a server. One lock around short writes is simpler than
        # a connection pool and fast enough for anything this will ever see.
        self._lock = threading.Lock()
        self._ensure_schema()

    # -----------------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """A connection that is always closed.

        `sqlite3.Connection` as a context manager commits — it does NOT close.
        Using it directly leaked a file handle per call, which on a long-running
        server is a slow exhaustion, and on Windows shows up immediately as a
        file that cannot be deleted. Committing and closing are separate jobs
        and this does both.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` only.

        Never a destructive migration: this database also holds the consent
        checkpoints, and a schema change that dropped a table would take an
        encounter's gate with it.
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {_MEMORY_TABLE} (
                    memory_id  TEXT PRIMARY KEY,
                    owner_id   TEXT NOT NULL,
                    scope      TEXT NOT NULL,
                    lockin_id  TEXT,
                    dimension  TEXT NOT NULL,
                    value      TEXT NOT NULL,
                    source     TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    active     INTEGER NOT NULL DEFAULT 1
                )"""
            )
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {_PLAN_TABLE} (
                    plan_id       TEXT PRIMARY KEY,
                    lockin_id     TEXT NOT NULL,
                    owner_id      TEXT NOT NULL,
                    shape         TEXT NOT NULL,
                    lead_venue_id TEXT NOT NULL,
                    budget_band   TEXT NOT NULL,
                    duration_band TEXT NOT NULL,
                    energy_band   TEXT NOT NULL,
                    formats       TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                )"""
            )
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {_FEEDBACK_TABLE} (
                    feedback_id TEXT PRIMARY KEY,
                    plan_id     TEXT NOT NULL,
                    lockin_id   TEXT NOT NULL,
                    owner_id    TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    reasons     TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    active      INTEGER NOT NULL DEFAULT 1
                )"""
            )
            # Reads are always by owner, so the index matches the access path.
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_memory_owner "
                f"ON {_MEMORY_TABLE} (owner_id, active)"
            )
            conn.commit()

    # -----------------------------------------------------------------
    # Memory
    # -----------------------------------------------------------------

    def remember(
        self,
        *,
        owner_id: str,
        scope: str,
        dimension: str,
        value: str,
        source: str,
        lockin_id: str | None = None,
        now: datetime | None = None,
    ) -> DateMemoryItem:
        """Write or reinforce one belief.

        UPSERT on (owner, scope, lock-in, dimension), so pressing Generate twice
        with the same constraints does not accumulate duplicate rows — the
        second write updates the first. Without that, "remember this" would
        silently become "remember this louder every time I use the app".

        Confidence moves according to where the belief came from:

          explicit — pinned to 1.0. The person said it; there is nothing to
                     estimate.
          feedback — climbs by `CONFIDENCE_STEP` toward the inferred cap, never
                     past it, so one rejection nudges and repetition persuades.
                     A single no is not a permanent dislike.

        An explicit statement OVERWRITES an inferred one. Being told beats
        having guessed, and a person who corrects Spark should not have to do it
        twice.

        The reverse never happens. An inferred belief that disagrees with a
        stated one is DISCARDED, not applied at low confidence: a preference
        somebody typed is not something Spark gets to talk itself out of by
        watching them.
        """
        now = now or datetime.now()
        memory_id = self._memory_id(owner_id, scope, lockin_id, dimension)

        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {_MEMORY_TABLE} WHERE memory_id = ?", (memory_id,)
            ).fetchone()

            if row is None:
                confidence = (
                    EXPLICIT_CONFIDENCE
                    if source == "explicit"
                    else min(CONFIDENCE_STEP, MAX_INFERRED_CONFIDENCE)
                )
                conn.execute(
                    f"INSERT INTO {_MEMORY_TABLE} (memory_id, owner_id, scope, "
                    "lockin_id, dimension, value, source, confidence, "
                    "created_at, updated_at, active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        memory_id, owner_id, scope, lockin_id, dimension, value,
                        source, confidence, now.isoformat(), now.isoformat(),
                    ),
                )
                conn.commit()
                return self._to_item(
                    conn.execute(
                        f"SELECT * FROM {_MEMORY_TABLE} WHERE memory_id = ?",
                        (memory_id,),
                    ).fetchone()
                )

            same_value = row["value"] == value
            if source == "explicit":
                confidence = EXPLICIT_CONFIDENCE
            elif row["source"] == "explicit" and not same_value:
                # SOMETHING INFERRED MAY NEVER OVERWRITE SOMETHING CHOSEN.
                #
                # Behaviour that argues against a stated preference is not
                # evidence the person changed their mind — they may have been
                # accommodating somebody else, or trying something once. Letting
                # it win would mean a person who typed "under $20" watches Spark
                # quietly stop believing them, with no screen anywhere that says
                # so and nothing to correct.
                #
                # The stated value stands, untouched. Changing it is a thing the
                # person does, on the preferences screen, on purpose.
                return self._to_item(row)
            elif not same_value:
                # They did something that argues for a different value. Move
                # toward it from a standing start rather than inheriting the
                # confidence built up for the old one.
                confidence = min(CONFIDENCE_STEP, MAX_INFERRED_CONFIDENCE)
            else:
                confidence = min(
                    row["confidence"] + CONFIDENCE_STEP, MAX_INFERRED_CONFIDENCE
                )
                if row["source"] == "explicit":
                    # Never quietly demote something the person told us.
                    confidence = EXPLICIT_CONFIDENCE
                    source = "explicit"

            conn.execute(
                f"UPDATE {_MEMORY_TABLE} SET value = ?, source = ?, "
                "confidence = ?, updated_at = ?, active = 1 WHERE memory_id = ?",
                (value, source, confidence, now.isoformat(), memory_id),
            )
            conn.commit()
            return self._to_item(
                conn.execute(
                    f"SELECT * FROM {_MEMORY_TABLE} WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
            )

    def for_owner(
        self, owner_id: str, lockin_id: str | None = None
    ) -> list[DateMemoryItem]:
        """Everything applicable, and nothing else.

        Returns this owner's `user` items plus the `lockin` items for THIS
        lock-in. Another lock-in's items are not returned, and neither is
        anybody else's anything — the WHERE clause is the boundary, so no caller
        can forget to apply it.
        """
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {_MEMORY_TABLE} WHERE owner_id = ? AND active = 1 "
                "AND (scope = 'user' OR lockin_id = ?) ORDER BY dimension, value",
                (owner_id, lockin_id),
            ).fetchall()
        return [self._to_item(r) for r in rows]

    def get(self, memory_id: str, owner_id: str) -> DateMemoryItem | None:
        """Scoped by owner as well as id, so guessing an id reveals nothing."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {_MEMORY_TABLE} WHERE memory_id = ? AND owner_id = ?",
                (memory_id, owner_id),
            ).fetchone()
        return self._to_item(row) if row else None

    def correct(
        self, memory_id: str, owner_id: str, value: str, now: datetime | None = None
    ) -> DateMemoryItem | None:
        """The person fixing what Spark believes.

        A correction is explicit by definition, so it takes explicit confidence:
        having been told, Spark should stop weighing what it had inferred.
        """
        now = now or datetime.now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE {_MEMORY_TABLE} SET value = ?, source = 'explicit', "
                "confidence = ?, updated_at = ?, active = 1 "
                "WHERE memory_id = ? AND owner_id = ?",
                (value, EXPLICIT_CONFIDENCE, now.isoformat(), memory_id, owner_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get(memory_id, owner_id)

    def forget(self, memory_id: str, owner_id: str) -> bool:
        """Soft delete. Nothing inactive is ever scored.

        Soft rather than hard so a deletion is recoverable and the audit trail
        stays readable — but `for_owner` filters on `active`, so as far as
        planning is concerned the belief is gone the moment it is deleted.
        """
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE {_MEMORY_TABLE} SET active = 0 "
                "WHERE memory_id = ? AND owner_id = ? AND active = 1",
                (memory_id, owner_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # -----------------------------------------------------------------
    # Plans
    # -----------------------------------------------------------------

    def record_plan(self, plan: DatePlanRecord) -> None:
        """Snapshot a plan that was shown.

        `INSERT OR REPLACE` keyed on a deterministic plan id, so regenerating
        with unchanged inputs overwrites rather than piling up — the same
        reasoning as the memory upsert.
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {_PLAN_TABLE} (plan_id, lockin_id, "
                "owner_id, shape, lead_venue_id, budget_band, duration_band, "
                "energy_band, formats, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    plan.plan_id, plan.lockin_id, plan.owner_id, plan.shape,
                    plan.lead_venue_id, plan.budget_band, plan.duration_band,
                    plan.energy_band, ",".join(plan.formats),
                    plan.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_plan(self, plan_id: str) -> DatePlanRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {_PLAN_TABLE} WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            return None
        return DatePlanRecord(
            plan_id=row["plan_id"],
            lockin_id=row["lockin_id"],
            owner_id=row["owner_id"],
            shape=row["shape"],
            lead_venue_id=row["lead_venue_id"],
            budget_band=row["budget_band"],
            duration_band=row["duration_band"],
            energy_band=row["energy_band"],
            formats=[f for f in row["formats"].split(",") if f],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # -----------------------------------------------------------------
    # Feedback
    # -----------------------------------------------------------------

    def record_feedback(self, feedback: DatePlanFeedback) -> DatePlanFeedback:
        """Append feedback, superseding anything earlier for the same plan.

        IDEMPOTENT BY DESIGN. The previous rows for this (plan, owner) are
        deactivated first, so submitting the same thing twice leaves one active
        row and changing your mind leaves the new one active with the old one
        still readable. Without this, a double-tap would count twice and the
        memory would drift on a UI accident.
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE {_FEEDBACK_TABLE} SET active = 0 "
                "WHERE plan_id = ? AND owner_id = ?",
                (feedback.plan_id, feedback.owner_id),
            )
            conn.execute(
                f"INSERT OR REPLACE INTO {_FEEDBACK_TABLE} (feedback_id, plan_id, "
                "lockin_id, owner_id, action, reasons, created_at, active) "
                "VALUES (?,?,?,?,?,?,?,1)",
                (
                    feedback.feedback_id, feedback.plan_id, feedback.lockin_id,
                    feedback.owner_id, feedback.action, ",".join(feedback.reasons),
                    feedback.created_at.isoformat(),
                ),
            )
            conn.commit()
        return feedback

    def feedback_for(self, owner_id: str, lockin_id: str) -> list[DatePlanFeedback]:
        """Active feedback only. Superseded rows stay on disk and out of the
        scorer."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {_FEEDBACK_TABLE} WHERE owner_id = ? "
                "AND lockin_id = ? AND active = 1 ORDER BY created_at",
                (owner_id, lockin_id),
            ).fetchall()
        return [
            DatePlanFeedback(
                feedback_id=r["feedback_id"],
                plan_id=r["plan_id"],
                lockin_id=r["lockin_id"],
                owner_id=r["owner_id"],
                action=r["action"],
                reasons=[x for x in r["reasons"].split(",") if x],
                created_at=datetime.fromisoformat(r["created_at"]),
                active=bool(r["active"]),
            )
            for r in rows
        ]

    # -----------------------------------------------------------------

    def clear(self) -> None:
        """Wipe Date Studio state, for the demo reset.

        Recorded takes have to be deterministic, and a preference learned during
        rehearsal would quietly change the ranking on camera. A RESTART must
        preserve everything; only an explicit reset clears it.

        Touches only Date Studio's own tables. The checkpoints share this file
        and are none of its business.
        """
        with self._lock, self._connect() as conn:
            for table in (_MEMORY_TABLE, _PLAN_TABLE, _FEEDBACK_TABLE):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()

    # -----------------------------------------------------------------
    @staticmethod
    def _memory_id(
        owner_id: str, scope: str, lockin_id: str | None, dimension: str
    ) -> str:
        """Deterministic, so the upsert has something stable to collide on.

        One belief per (owner, scope, lock-in, dimension): a person has one
        budget preference, not a growing list of them.
        """
        return f"mem:{owner_id}:{scope}:{lockin_id or '-'}:{dimension}"

    @staticmethod
    def _to_item(row: sqlite3.Row) -> DateMemoryItem:
        return DateMemoryItem(
            memory_id=row["memory_id"],
            owner_id=row["owner_id"],
            scope=row["scope"],
            lockin_id=row["lockin_id"],
            dimension=row["dimension"],
            value=row["value"],
            source=row["source"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            active=bool(row["active"]),
        )
