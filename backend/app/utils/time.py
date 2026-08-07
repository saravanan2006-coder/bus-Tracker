"""Time helpers that normalise between SQLite (naive) and Postgres (aware)."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Return `dt` as a timezone-aware UTC datetime regardless of source.

    SQLite returns naive datetimes; PostgreSQL returns aware ones. This
    normalises both before any in-Python comparison.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
