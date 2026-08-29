"""Simulated time.

Nothing in Spark calls `datetime.now()`. A six-week run has to be reproducible
— the same seed must produce the same encounters, the same declines and the
same numbers — and it has to complete in seconds rather than in six weeks.

The clock is passed in, never imported ambiently, so a test can place an
encounter on any day it likes and assert on exact timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, time, timedelta

from src.schemas.core import TimeBucket

#: Representative hour for each coarse bucket. Used to place a simulated call
#: inside a day. Never rendered — a bucket is what a user sees, if anything.
_BUCKET_HOUR: dict[TimeBucket, int] = {
    TimeBucket.EARLY_MORNING: 6,
    TimeBucket.MORNING: 9,
    TimeBucket.MIDDAY: 12,
    TimeBucket.AFTERNOON: 15,
    TimeBucket.EVENING: 19,
    TimeBucket.NIGHT: 22,
}


@dataclass
class SimClock:
    """A deterministic clock over simulated days.

    `day_zero` is the first simulated day. `advance()` moves to the next one.
    Every timestamp in a run is derived from these two facts, which is why a
    run is reproducible from a seed alone.
    """

    day_zero: Date
    current: Date

    def __init__(self, day_zero: Date) -> None:
        self.day_zero = day_zero
        self.current = day_zero

    def advance(self, days: int = 1) -> Date:
        self.current = self.current + timedelta(days=days)
        return self.current

    def at(self, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(self.current, time(hour=hour, minute=minute))

    def at_bucket(self, bucket: TimeBucket, minute: int = 0) -> datetime:
        return self.at(_BUCKET_HOUR[bucket], minute)

    @property
    def day_index(self) -> int:
        return (self.current - self.day_zero).days

    @property
    def week_index(self) -> int:
        """1-based week number. Week 1 is days 0-6.

        1-based because the deck says "week 5 behaves differently from week 1",
        and an off-by-one in that sentence is an off-by-one in the demo.
        """
        return self.day_index // 7 + 1

    def days_since(self, when: datetime | Date) -> int:
        other = when.date() if isinstance(when, datetime) else when
        return (self.current - other).days
