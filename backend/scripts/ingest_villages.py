"""Production village/town ingestion CLI.

Usage:
    python -m scripts.ingest_villages --census data/census_villupuram.csv \
        --district Villupuram

Pipeline: parse census CSV -> merge -> reconcile against expected per-taluk
counts -> upsert. Publishing is blocked when the reconciliation report has
any taluk with fewer villages than expected.

The CSV layout mirrors the Census 2011 Village Directory extract plus
optional lat/lng and Tamil names (see data/fixtures/villupuram_taluks.csv).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, init_db
from app.models import District, Taluk, Village
from app.services.village_pipeline import (
    build_reconciliation_report,
    merge_village_sources,
    normalize_name,
    parse_census_csv,
)

logger = logging.getLogger(__name__)


async def upsert(
    db: AsyncSession,
    district_name: str,
    records,
    expected_by_taluk: dict[str, int],
) -> dict:
    merged, _ = merge_village_sources(records)
    report = build_reconciliation_report(district_name, merged, expected_by_taluk)
    if report.blocks_publishing:
        logger.error(
            "RECONCILIATION BLOCKED: missing villages for district %s. %s",
            district_name,
            report.to_dict(),
        )
        return {"loaded": False, "reconciliation": report.to_dict()}

    district = await db.scalar(select(District).where(District.name == district_name))
    if district is None:
        district = District(name=district_name)
        db.add(district)
        await db.flush()

    taluk_cache: dict[str, Taluk] = {}
    created = 0
    for rec in merged.values():
        taluk_name = rec.taluk or "Unknown"
        if taluk_name not in taluk_cache:
            taluk = await db.scalar(
                select(Taluk).where(
                    Taluk.district_id == district.id, Taluk.name == taluk_name
                )
            )
            if taluk is None:
                taluk = Taluk(district_id=district.id, name=taluk_name)
                db.add(taluk)
                await db.flush()
            taluk_cache[taluk_name] = taluk
        taluk = taluk_cache[taluk_name]

        village = await db.scalar(
            select(Village).where(
                Village.taluk_id == taluk.id,
                Village.name_normalized == normalize_name(rec.name),
            )
        )
        if village is None:
            village = Village(
                district_id=district.id,
                taluk_id=taluk.id,
                name=rec.name,
                name_normalized=normalize_name(rec.name),
                name_ta=rec.name_ta,
                lat=rec.lat,
                lng=rec.lng,
                has_coords=rec.lat is not None and rec.lng is not None,
                census_code=rec.census_code,
                place_type=rec.place_type,
                source="|".join(rec.sources),
                needs_review=not (rec.lat is not None and rec.lng is not None),
            )
            db.add(village)
            created += 1
        else:
            if rec.lat is not None and rec.lng is not None:
                village.lat, village.lng = rec.lat, rec.lng
                village.has_coords = True
            if rec.name_ta:
                village.name_ta = rec.name_ta
    await db.commit()
    logger.info("Loaded %s new villages for %s", created, district_name)
    return {"loaded": True, "created": created, "reconciliation": report.to_dict()}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", required=True, help="Path to census CSV extract")
    parser.add_argument("--district", required=True, help="District name")
    parser.add_argument(
        "--expected",
        help="Comma-separated taluk=count pairs, e.g. Tindivanam=120,Villupuram=95",
    )
    parser.add_argument(
        "--expected-file",
        help="CSV of taluk,expected rows (e.g. data/fixtures/villupuram_expected.csv)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    with open(args.census, encoding="utf-8") as fh:
        records = parse_census_csv(fh.read())
    logger.info("Parsed %s records from census CSV", len(records))

    expected = {}
    if args.expected:
        for pair in args.expected.split(","):
            taluk, count = pair.split("=")
            expected[taluk.strip()] = int(count)
    elif args.expected_file:
        with open(args.expected_file, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                taluk = (row.get("taluk") or "").strip()
                if taluk:
                    expected[taluk] = int(row["expected"])

    await init_db()
    async with SessionLocal() as session:
        result = await upsert(session, args.district, records, expected)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
