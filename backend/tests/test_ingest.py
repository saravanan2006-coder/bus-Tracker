"""Ingest tests: upsert must persist every census village, never silently
merge same-name villages that carry different official codes."""
from __future__ import annotations

from sqlalchemy import select

from app.models import District, Taluk, Village
from app.services.village_pipeline import SourceRecord
from scripts.ingest_villages import upsert


async def test_upsert_persists_same_name_distinct_codes(db):
    recs = [
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="101", source="tn-census",
        ),
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="203", source="tn-census",
        ),
    ]
    result = await upsert(db, "Madurai", recs, {"Madurai North": 2})
    assert result["loaded"] is True
    assert result["created"] == 2
    assert result["reconciliation"]["blocks_publishing"] is False

    district = await db.scalar(select(District).where(District.name == "Madurai"))
    taluk = await db.scalar(
        select(Taluk).where(
            Taluk.district_id == district.id, Taluk.name == "Madurai North"
        )
    )
    villages = (
        await db.scalars(
            select(Village).where(Village.taluk_id == taluk.id)
        )
    ).all()
    by_code = {v.census_code: v for v in villages if v.census_code}
    assert set(by_code) == {"101", "203"}
    assert by_code["101"].name == "Arumbanur"
    assert by_code["203"].name == "Arumbanur"
    # The seeded Madurai city still shares the taluk untouched.
    assert any(v.name == "Madurai" for v in villages)


async def test_upsert_updates_by_code_not_name(db):
    recs = [
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="101", source="tn-census",
        ),
    ]
    result = await upsert(db, "Madurai", recs, {"Madurai North": 1})
    assert result["created"] == 1

    # Re-ingest the same code with coordinates: the existing row is updated,
    # not duplicated, and the second code lands as its own row.
    recs = [
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="101", lat=9.95, lng=78.12, source="tn-census",
        ),
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="203", source="tn-census",
        ),
    ]
    result = await upsert(db, "Madurai", recs, {"Madurai North": 2})
    assert result["loaded"] is True
    assert result["created"] == 1

    district = await db.scalar(select(District).where(District.name == "Madurai"))
    taluk = await db.scalar(
        select(Taluk).where(
            Taluk.district_id == district.id, Taluk.name == "Madurai North"
        )
    )
    villages = (
        await db.scalars(
            select(Village).where(Village.taluk_id == taluk.id)
        )
    ).all()
    by_code = {v.census_code: v for v in villages if v.census_code}
    assert set(by_code) == {"101", "203"}
    assert by_code["101"].lat == 9.95
    assert by_code["101"].has_coords is True


async def test_upsert_blocks_when_village_missing(db):
    recs = [
        SourceRecord(
            name="Arumbanur", taluk="Madurai North", district="Madurai",
            census_code="101", source="tn-census",
        ),
    ]
    # Expected says two villages for this taluk; only one is present.
    result = await upsert(db, "Madurai", recs, {"Madurai North": 2})
    assert result["loaded"] is False
    assert result["reconciliation"]["blocks_publishing"] is True
