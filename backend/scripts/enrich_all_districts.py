"""Fetch OSM place extracts and enrich every Census-2011 district.

Usage (from backend/):
    python -m scripts.enrich_all_districts --input ../tn_dist_blk_vill_hab_0_1.csv
    python -m scripts.enrich_all_districts --only Ariyalur,Kancheepuram
    python -m scripts.enrich_all_districts --sleep 5

For each district this runs build_osm_extract (Overpass fetch) then
ingest_tn_census (rebase expected counts, attach coordinates by unambiguous
name match, merge urban towns, upsert). Both steps are idempotent, so a
re-run upgrades coordinates without duplicating rows. Each district is
independent: a failure there is reported and the run continues.

The OSM admin-area name can differ from the census spelling (e.g. census
"Tiruvallur" is OSM "Thiruvallur"); the mapping below is keyed by census
name. Modern OSM district areas that were split off since the 2019 Census
(e.g. Chengalpattu, Kallakurichi) are not separate entries: enrichment uses
the pre-split census district, so the extract for the surviving area is the
coordinate source, and villages in the split-off part simply stay flagged
until their own area is added.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

# (census/DB district name, TN census district code, OSM admin-area name)
DISTRICTS: list[tuple[str, str, str]] = [
    ("Kancheepuram", "1", "Kanchipuram"),
    ("Tiruvallur", "2", "Thiruvallur"),
    ("Cuddalore", "3", "Cuddalore"),
    ("Villupuram", "4", "Viluppuram"),
    ("Vellore", "5", "Vellore"),
    ("Tiruvannamalai", "6", "Tiruvannamalai"),
    ("Salem", "7", "Salem"),
    ("Namakkal", "8", "Namakkal"),
    ("Dharmapuri", "9", "Dharmapuri"),
    ("Erode", "10", "Erode"),
    ("Coimbatore", "11", "Coimbatore"),
    ("The Nilgiris", "12", "Nilgiris"),
    ("Thanjavur", "13", "Thanjavur"),
    ("Nagapattinam", "14", "Nagapattinam"),
    ("Tiruvarur", "15", "Thiruvarur"),
    ("Tiruchirappalli", "16", "Tiruchirappalli"),
    ("Karur", "17", "Karur"),
    ("Perambalur", "18", "Perambalur"),
    ("Pudukkottai", "19", "Pudukkottai"),
    ("Madurai", "20", "Madurai"),
    ("Theni", "21", "Theni"),
    ("Dindigul", "22", "Dindigul"),
    ("Ramanathapuram", "23", "Ramanathapuram"),
    ("Virudhunagar", "24", "Virudhunagar"),
    ("Sivagangai", "25", "Sivagangai"),
    ("Tirunelveli", "26", "Tirunelveli"),
    ("Thoothukkudi", "27", "Thoothukudi"),
    ("Kanniyakumari", "28", "Kanniyakumari"),
    ("Krishnagiri", "30", "Krishnagiri"),
    ("Ariyalur", "31", "Ariyalur"),
    ("Tiruppur", "32", "Tiruppur"),
]


def slug(name: str) -> str:
    from slugify import slugify

    return slugify(name, lowercase=True)


def run_step(cmd: list[str], retries: int = 3) -> subprocess.CompletedProcess:
    last = None
    for attempt in range(1, retries + 1):
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            return proc
        last = proc
        wait = 10 * attempt
        print(f"    attempt {attempt}/{retries} failed, retrying in {wait}s", flush=True)
        time.sleep(wait)
    return last  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, help="TN district-block-village-habitation CSV"
    )
    parser.add_argument(
        "--only",
        help="Comma-separated district names to process (resume/spot checks)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=30.0,
        help="Seconds to pause between districts (Overpass public API "
        "allows ~2 queries/min; each district issues one query)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Skip the Overpass fetch and reuse existing data/census_<slug>.csv",
    )
    args = parser.parse_args()

    wanted = (
        {slug(n) for n in args.only.split(",")} if args.only else None
    )
    selected = [
        d for d in DISTRICTS
        if wanted is None or slug(d[0]) in wanted
    ]
    if not selected:
        print("No districts matched --only", flush=True)
        return

    ok, failed = 0, 0
    for name, code, area in selected:
        print(f"== {name} (census {code}, OSM '{area}') ==", flush=True)
        slug_name = slug(name)
        extract = f"data/census_{slug_name}.csv"
        fixture = f"data/fixtures/{slug_name}_expected.csv"
        try:
            if not args.no_extract:
                proc = run_step(
                    [
                        sys.executable, "-m", "scripts.build_osm_extract",
                        "--district", name,
                        "--area-name", area,
                        "--out", extract,
                    ]
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"build_osm_extract failed: {proc.stderr.strip()[-400:]}"
                    )
                first = proc.stdout.strip().splitlines() or ["(no output)"]
                print("  extract:", first[0], flush=True)
            proc = run_step(
                [
                    sys.executable, "-m", "scripts.ingest_tn_census",
                    "--input", args.input,
                    "--district", name,
                    "--district-code", code,
                    "--osm", extract,
                    "--expected-file", fixture,
                ]
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ingest_tn_census failed: {proc.stderr.strip()[-400:]}"
                )
            lines = proc.stdout.strip().splitlines()
            print("  ingest:", lines[-1] if lines else "(no output)", flush=True)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  FAILED: {exc}", flush=True)
            failed += 1
        time.sleep(args.sleep)

    print(f"\nDone: {ok} ok, {failed} failed", flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
