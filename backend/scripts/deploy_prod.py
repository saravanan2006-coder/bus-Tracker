"""One-shot production deployment: migrate + ingest + seed.

Run against a Postgres DATABASE_URL (must be set, must NOT be SQLite):

    DATABASE_URL=postgresql+asyncpg://user:pass@host/db python -m scripts.deploy_prod

Steps (each fails loudly and stops the run):
    1. apply pending SQL migrations      (scripts.migrate)
    2. ingest all 31 districts           (scripts.enrich_all_districts --no-extract,
                                         reusing the saved OSM extracts in data/)
    3. seed demo data                    (app.seed.demo_data)

Ingest is idempotent (census rows match by official code), so re-running on
an already-loaded database only upgrades coordinates and adds nothing new.

Options:
    --only A,B        ingest a subset of districts (spot checks)
    --skip-migrate    assume the schema is already applied
    --skip-seed       do not seed demo data
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
REPO = BACKEND.parent


def run_step(cmd: list[str], label: str) -> None:
    print(f"\n== {label} ==", flush=True)
    proc = subprocess.run(
        cmd, cwd=BACKEND, env=dict(os.environ),
        capture_output=True, text=True, timeout=3600,
    )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln][-4:]
    if tail:
        print("\n".join(tail), flush=True)
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip()[-2000:], file=sys.stderr)
        raise SystemExit(f"{label} FAILED (exit {proc.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="Comma-separated districts to ingest")
    parser.add_argument("--skip-migrate", action="store_true")
    parser.add_argument("--skip-seed", action="store_true")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    if "sqlite" in url.lower():
        raise SystemExit("DATABASE_URL must point at PostgreSQL, not SQLite")

    census = REPO / "tn_dist_blk_vill_hab_0_1.csv"
    if not census.exists():
        raise SystemExit(f"census file not found: {census}")

    if not args.skip_migrate:
        run_step([sys.executable, "-m", "scripts.migrate"], "apply SQL migrations")

    ingest = [
        sys.executable, "-m", "scripts.enrich_all_districts",
        "--input", str(census), "--no-extract",
    ]
    if args.only:
        ingest += ["--only", args.only]
    run_step(ingest, "ingest districts (reusing saved OSM extracts)")

    if not args.skip_seed:
        run_step([sys.executable, "-m", "app.seed.demo_data"], "seed demo data")

    print(
        "\nDeploy steps completed. Next: check GET /health and "
        "GET /api/v1/admin/stats on the live instance.",
        flush=True,
    )


if __name__ == "__main__":
    main()
