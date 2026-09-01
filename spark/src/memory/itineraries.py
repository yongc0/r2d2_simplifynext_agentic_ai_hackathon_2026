"""Durable itineraries, and the private reflections written after them.

Same database file as the graph checkpoints and Date Studio's memory, for the
reason given in `date_memory.py`: a plan that outlives the encounter it belongs
to is a worse state than no plan at all.

TWO TABLES, TWO VERY DIFFERENT PRIVACY POSTURES

`itineraries` is shared ground. Both people are meant to see the plan; that is
what a plan is for.

`reflections` is not, and is the reason this module exists rather than another
column on the plan. Every read path takes an `owner_id` and filters on it, there
is no method that returns another person's reflection, and there is no aggregate
— no average, no count, no "how are your dates going" figure — because any
aggregate over two people is differenceable back to one of them. A person who
answers "no" to "would you see them again" must be able to do that honestly, and
that is only true if the answer cannot travel.

THE STORED SHAPE IS THE MODEL

An itinerary is written as its own validated JSON rather than exploded into
columns. The nested stops, travel legs and times are one document that is only
ever read whole, and a schema that mirrored them in SQL would let a row exist
that `DateItinerary` would refuse to construct — which is precisely the
guarantee the model is there to give.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from src.schemas.itinerary import DateItinerary, DateReflection

_ITINERARY_TABLE = "date_itineraries"
_REFLECTION_TABLE = "date_reflections"


class ItineraryStore:
    """Plans and reflections on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._ensure_schema()

    # -----------------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """A connection that is always closed — see `DateMemoryStore._connect`."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` only. Never a destructive migration:
        the consent checkpoints share this file."""
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {_ITINERARY_TABLE} (
                    itinerary_id TEXT PRIMARY KEY,
                    lockin_id    TEXT NOT NULL,
                    owner_id     TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    document     TEXT NOT NULL
                )"""
            )
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {_REFLECTION_TABLE} (
                    reflection_id TEXT PRIMARY KEY,
                    itinerary_id  TEXT NOT NULL,
                    lockin_id     TEXT NOT NULL,
                    owner_id      TEXT NOT NULL,
                    overall       INTEGER NOT NULL,
                    ratings       TEXT NOT NULL,
                    second_date   TEXT NOT NULL,
                    notes         TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    active        INTEGER NOT NULL DEFAULT 1
                )"""
            )
            # Both access paths are "this person's, newest first".
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_itin_owner "
                f"ON {_ITINERARY_TABLE} (owner_id, updated_at)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_reflection_owner "
                f"ON {_REFLECTION_TABLE} (owner_id, active)"
            )
            conn.commit()

    # -----------------------------------------------------------------
    # Itineraries
    # -----------------------------------------------------------------

    def save(self, itinerary: DateItinerary) -> DateItinerary:
        """Insert or replace, by id. Regenerating a stop keeps the same id and
        therefore the same row — the plan is edited, not duplicated."""
        stamped = itinerary.model_copy(update={"updated_at": datetime.now(UTC)})
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""INSERT INTO {_ITINERARY_TABLE}
                    (itinerary_id, lockin_id, owner_id, status,
                     created_at, updated_at, document)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(itinerary_id) DO UPDATE SET
                      status     = excluded.status,
                      updated_at = excluded.updated_at,
                      document   = excluded.document""",
                (
                    stamped.itinerary_id,
                    stamped.lockin_id,
                    stamped.owner_id,
                    stamped.status,
                    stamped.created_at.isoformat(),
                    stamped.updated_at.isoformat(),
                    stamped.model_dump_json(),
                ),
            )
            conn.commit()
        return stamped

    def get(self, itinerary_id: str, owner_id: str) -> DateItinerary | None:
        """One plan, and only if it is this viewer's.

        `owner_id` is a filter rather than an assertion afterwards, so a wrong
        owner is indistinguishable from a missing plan. A 403 would confirm that
        somebody else's plan exists under that id.
        """
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT document FROM {_ITINERARY_TABLE} "
                f"WHERE itinerary_id = ? AND owner_id = ?",
                (itinerary_id, owner_id),
            ).fetchone()
        return DateItinerary.model_validate_json(row["document"]) if row else None

    def for_owner(
        self, owner_id: str, lockin_id: str | None = None
    ) -> list[DateItinerary]:
        """This person's plans, newest first. Optionally one connection's."""
        query = f"SELECT document FROM {_ITINERARY_TABLE} WHERE owner_id = ?"
        params: list[str] = [owner_id]
        if lockin_id is not None:
            query += " AND lockin_id = ?"
            params.append(lockin_id)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [DateItinerary.model_validate_json(r["document"]) for r in rows]

    def set_status(
        self, itinerary_id: str, owner_id: str, status: str
    ) -> DateItinerary | None:
        """Move a plan along its life. Returns `None` if it is not this
        viewer's, for the same reason `get` does."""
        existing = self.get(itinerary_id, owner_id)
        if existing is None:
            return None
        return self.save(existing.model_copy(update={"status": status}))

    # -----------------------------------------------------------------
    # Reflections
    # -----------------------------------------------------------------

    def record_reflection(
        self,
        *,
        itinerary_id: str,
        lockin_id: str,
        owner_id: str,
        overall: int,
        ratings: dict[str, int],
        second_date: str,
        notes: str,
    ) -> DateReflection:
        """Store how a date went, for the person who was on it.

        Idempotent per (itinerary, owner): a previous reflection is deactivated
        rather than deleted before the new one lands, so changing your mind
        leaves one live answer with the old one still readable. Two rows would
        double-count in `signals_for`, and a recommender that shifts twice
        because somebody tapped twice is learning from the interface rather than
        from the person.
        """
        reflection = DateReflection(
            reflection_id=f"refl-{uuid.uuid4().hex[:12]}",
            itinerary_id=itinerary_id,
            lockin_id=lockin_id,
            owner_id=owner_id,
            overall=overall,
            ratings=ratings,  # type: ignore[arg-type]
            second_date=second_date,  # type: ignore[arg-type]
            notes=notes,
            created_at=datetime.now(UTC),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE {_REFLECTION_TABLE} SET active = 0 "
                f"WHERE itinerary_id = ? AND owner_id = ?",
                (itinerary_id, owner_id),
            )
            conn.execute(
                f"""INSERT INTO {_REFLECTION_TABLE}
                    (reflection_id, itinerary_id, lockin_id, owner_id, overall,
                     ratings, second_date, notes, created_at, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    reflection.reflection_id,
                    reflection.itinerary_id,
                    reflection.lockin_id,
                    reflection.owner_id,
                    reflection.overall,
                    json.dumps(reflection.ratings),
                    reflection.second_date,
                    reflection.notes,
                    reflection.created_at.isoformat(),
                ),
            )
            conn.commit()
        return reflection

    def reflection_for(
        self, itinerary_id: str, owner_id: str
    ) -> DateReflection | None:
        """This viewer's own reflection on one date, if they wrote one.

        There is deliberately no variant of this that takes a lock-in and
        returns everybody's. Nothing in Spark may read a reflection that is not
        the caller's own.
        """
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {_REFLECTION_TABLE} "
                f"WHERE itinerary_id = ? AND owner_id = ? AND active = 1",
                (itinerary_id, owner_id),
            ).fetchone()
        return self._to_reflection(row) if row else None

    def reflections_for_owner(self, owner_id: str) -> list[DateReflection]:
        """Everything this person has written, newest first. Theirs only."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {_REFLECTION_TABLE} "
                f"WHERE owner_id = ? AND active = 1 ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        return [self._to_reflection(row) for row in rows]

    def forget_reflection(self, reflection_id: str, owner_id: str) -> bool:
        """Soft delete. Nothing reads an inactive row, and the audit trail
        stays legible."""
        with self._lock, self._connect() as conn:
            changed = conn.execute(
                f"UPDATE {_REFLECTION_TABLE} SET active = 0 "
                f"WHERE reflection_id = ? AND owner_id = ? AND active = 1",
                (reflection_id, owner_id),
            ).rowcount
            conn.commit()
        return bool(changed)

    # -----------------------------------------------------------------

    def clear(self) -> None:
        """Wipe both tables, for the demo reset. Touches nothing else in the
        file — the checkpoints share it and are none of this store's business."""
        with self._lock, self._connect() as conn:
            for table in (_ITINERARY_TABLE, _REFLECTION_TABLE):
                conn.execute(f"DELETE FROM {table}")
            conn.commit()

    @staticmethod
    def _to_reflection(row: sqlite3.Row) -> DateReflection:
        return DateReflection(
            reflection_id=row["reflection_id"],
            itinerary_id=row["itinerary_id"],
            lockin_id=row["lockin_id"],
            owner_id=row["owner_id"],
            overall=row["overall"],
            ratings=json.loads(row["ratings"]),
            second_date=row["second_date"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            active=bool(row["active"]),
        )
