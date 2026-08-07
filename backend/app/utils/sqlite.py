"""Cross-dialect JSON column type.

SQLite has no native JSON type; this stores JSON documents as TEXT while
keeping the same ORM semantics as PostgreSQL's JSONB.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.types import TEXT, TypeDecorator


class JSONType(TypeDecorator):
    """Stores Python objects as JSON text on SQLite / native JSONB on PG."""

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value: Any | None, dialect) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect) -> Any | None:
        if value is None:
            return None
        return json.loads(value)
