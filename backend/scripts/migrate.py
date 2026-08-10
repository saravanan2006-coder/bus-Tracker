"""Apply the tracked SQL migrations in backend/migrations to the database.

The migration files are PostgreSQL/PostGIS-specific. Each file runs at most
once: a `schema_migrations` ledger records what has been applied, so re-runs
are safe and additive migrations are discovered automatically. SQLite
(dev/tests) is not migrated here -- the ORM's create_all builds that schema.

Usage:
    python -m scripts.migrate                  # uses DATABASE_URL
    DATABASE_URL=postgresql+asyncpg://u:p@host/db python -m scripts.migrate
    python -m scripts.migrate --dry-run        # list pending files only
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def split_statements(sql: str) -> list[str]:
    """Split SQL on terminators, ignoring semicolons inside string literals
    and line comments (Postgres dollar-quoted strings are not used here)."""
    statements: list[str] = []
    buf: list[str] = []
    in_string = False
    in_line_comment = False
    i = 0
    while i < len(sql):
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            buf.append(c)
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_string:
            buf.append(c)
            if c == "'":
                if nxt == "'":  # escaped quote inside a literal
                    buf.append(nxt)
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if c == "-" and nxt == "-":
            in_line_comment = True
            buf.append(c)
            i += 1
            continue
        if c == "'":
            in_string = True
            buf.append(c)
            i += 1
            continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        statements.append(stmt)
    return [
        s for s in statements
        if any(
            ln and not ln.startswith("--")
            for ln in (line.strip() for line in s.splitlines())
        )
    ]


async def migrate(database_url: str, dry_run: bool) -> int:
    if "sqlite" in database_url:
        print(
            "SQLite database: migrations are Postgres-specific; the ORM's "
            "create_all builds the dev/test schema instead. Nothing to do."
        )
        return 0

    engine = create_async_engine(database_url)
    applied = 0
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "filename VARCHAR(255) PRIMARY KEY,"
                    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
            rows = (
                await conn.execute(text("SELECT filename FROM schema_migrations"))
            ).all()
        done = {r[0] for r in rows}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                print(f"skipping {path.name} (already applied)")
                continue
            if dry_run:
                print(f"would apply {path.name}")
                applied += 1
                continue
            statements = split_statements(path.read_text(encoding="utf-8"))
            async with engine.begin() as conn:
                for stmt in statements:
                    await conn.execute(text(stmt))
                await conn.execute(
                    text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                    {"f": path.name},
                )
            print(f"applied {path.name} ({len(statements)} statements)")
            applied += 1
    finally:
        await engine.dispose()
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="SQLAlchemy async URL (default: DATABASE_URL env var)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import os

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set (or pass --database-url).", file=__import__("sys").stderr)
        raise SystemExit(1)

    applied = asyncio.run(migrate(url, args.dry_run))
    print(f"{applied} migration(s) pending/applied")


if __name__ == "__main__":
    main()
