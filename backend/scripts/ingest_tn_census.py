"""Ingest the TN e-Governance district-block-village-habitation CSV.

Usage:
    python -m scripts.ingest_tn_census \
        --input ../../tn_dist_blk_vill_hab_0_1.csv \
        --district Villupuram \
        --osm data/census_villupuram.csv \
        --expected-file data/fixtures/villupuram_expected.csv

Pipeline: parse the authoritative block/village list (habitation rows
collapsed) -> rebase the expected per-taluk counts on the file itself ->
enrich coordinates from the OSM extract via unambiguous name match ->
merge unmatched OSM places (urban towns) into the nearest block ->
upsert. Publishing is blocked while any block falls short of the file, so
the full government list must land before the district goes live.

The block name becomes the taluk: this file predates the 2019 district
split and has no taluk column.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging

from app.database import SessionLocal, init_db
from app.services.village_pipeline import (
    census_expected_by_taluk,
    enrich_with_osm_coords,
    merge_osm_places,
    parse_census_csv,
    parse_tn_census_csv,
)
from scripts.ingest_villages import upsert

logger = logging.getLogger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, help="TN district-block-village-habitation CSV"
    )
    parser.add_argument("--district", default="Villupuram")
    parser.add_argument(
        "--district-code",
        default="4",
        help="District code to scope the ingest to (4 = Villupuram)",
    )
    parser.add_argument(
        "--osm",
        help=(
            "OSM-extract census CSV used to attach coordinates and to fill "
            "urban towns missing from the census file"
        ),
    )
    parser.add_argument(
        "--expected-file", help="Where to write the rebased expected fixture"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    with open(args.input, encoding="utf-8") as fh:
        records = parse_tn_census_csv(fh.read(), district_code=args.district_code)
    logger.info("Parsed %s authoritative villages from %s", len(records), args.input)

    expected = census_expected_by_taluk(records)
    if args.expected_file:
        with open(args.expected_file, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["taluk", "expected"])
            writer.writeheader()
            for taluk, count in expected.items():
                writer.writerow({"taluk": taluk, "expected": count})
        logger.info("Wrote expected fixture %s (%s taluks)", args.expected_file, len(expected))

    if args.osm:
        with open(args.osm, encoding="utf-8") as fh:
            osm_records = parse_census_csv(fh.read())
        records = enrich_with_osm_coords(records, osm_records)
        records = merge_osm_places(records, osm_records)
        with_coords = sum(1 for r in records if r.has_coords)
        logger.info(
            "Attached coordinates to %s/%s villages after OSM merge",
            with_coords,
            len(records),
        )

    await init_db()
    async with SessionLocal() as session:
        result = await upsert(session, args.district, records, expected)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
