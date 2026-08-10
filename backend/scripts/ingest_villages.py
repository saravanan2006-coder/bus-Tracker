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


# Curated Tamil names for the 31 Census-2011 districts. Shown in the
# passenger district picker when the app is in Tamil mode.
DISTRICT_NAME_TA = {
    "Kancheepuram": "காஞ்சிபுரம்",
    "Tiruvallur": "திருவள்ளூர்",
    "Cuddalore": "கடலூர்",
    "Villupuram": "விழுப்புரம்",
    "Vellore": "வேலூர்",
    "Tiruvannamalai": "திருவண்ணாமலை",
    "Salem": "சேலம்",
    "Namakkal": "நாமக்கல்",
    "Dharmapuri": "தருமபுரி",
    "Erode": "ஈரோடு",
    "Coimbatore": "கோயம்புத்தூர்",
    "The Nilgiris": "நீலகிரி",
    "Thanjavur": "தஞ்சாவூர்",
    "Nagapattinam": "நாகப்பட்டினம்",
    "Tiruvarur": "திருவாரூர்",
    "Tiruchirappalli": "திருச்சிராப்பள்ளி",
    "Karur": "கரூர்",
    "Perambalur": "பெரம்பலூர்",
    "Pudukkottai": "புதுக்கோட்டை",
    "Madurai": "மதுரை",
    "Theni": "தேனி",
    "Dindigul": "திண்டுக்கல்",
    "Ramanathapuram": "இராமநாதபுரம்",
    "Virudhunagar": "விருதுநகர்",
    "Sivagangai": "சிவகங்கை",
    "Tirunelveli": "திருநெல்வேலி",
    "Thoothukkudi": "தூத்துக்குடி",
    "Kanniyakumari": "கன்னியாகுமரி",
    "Krishnagiri": "கிருஷ்ணகிரி",
    "Ariyalur": "அரியலூர்",
    "Tiruppur": "திருப்பூர்",
}


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
        district = District(
            name=district_name, name_ta=DISTRICT_NAME_TA.get(district_name)
        )
        db.add(district)
        await db.flush()
    elif not district.name_ta:
        district.name_ta = DISTRICT_NAME_TA.get(district_name)

    # Load the district's taluks and villages in a handful of queries instead
    # of one round-trip per record (the previous loop issued ~2k SELECTs for a
    # large district, which took minutes against remote Postgres).
    taluks = (
        await db.scalars(select(Taluk).where(Taluk.district_id == district.id))
    ).all()
    taluk_by_name = {t.name: t for t in taluks}
    for rec in merged.values():
        taluk_name = rec.taluk or "Unknown"
        if taluk_name not in taluk_by_name:
            taluk_by_name[taluk_name] = Taluk(
                district_id=district.id, name=taluk_name
            )
            db.add(taluk_by_name[taluk_name])
    await db.flush()  # assign taluk ids for the village lookups below

    villages = (
        await db.scalars(select(Village).where(Village.district_id == district.id))
    ).all()
    # The official census code is the stable identity: two villages in one
    # taluk can share a name but carry different codes, and looking them up
    # by name alone would silently merge a listed village. Towns (no code)
    # fall back to the name match.
    by_code: dict[tuple[int, str], Village] = {}
    by_name: dict[tuple[int, str], Village] = {}
    for v in villages:
        if v.census_code:
            by_code[(v.taluk_id, v.census_code)] = v
        else:
            by_name[(v.taluk_id, v.name_normalized)] = v

    created = 0
    new_villages: list[Village] = []
    for rec in merged.values():
        taluk = taluk_by_name[rec.taluk or "Unknown"]
        if rec.census_code:
            village = by_code.get((taluk.id, rec.census_code))
        else:
            village = by_name.get((taluk.id, normalize_name(rec.name)))
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
            new_villages.append(village)
            created += 1
            # Register it so a later record with the same identity updates the
            # same in-memory object instead of creating a duplicate row.
            if rec.census_code:
                by_code[(taluk.id, rec.census_code)] = village
            else:
                by_name[(taluk.id, normalize_name(rec.name))] = village
        else:
            if rec.lat is not None and rec.lng is not None:
                village.lat, village.lng = rec.lat, rec.lng
                village.has_coords = True
                village.needs_review = False
            if rec.name_ta:
                village.name_ta = rec.name_ta
            if rec.place_type and rec.place_type != "village":
                village.place_type = rec.place_type
    db.add_all(new_villages)
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
