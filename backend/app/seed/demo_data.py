"""Demo seed data: real Tamil Nadu districts, taluks and towns.

NOTE: The villages used in this demo are real towns in Tamil Nadu. The two
example villages from the product discussion are intentionally NOT included.
Coordinates are approximate and exist so the full tracking flow can be
exercised end-to-end before the complete census/OSM pipeline is loaded.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, init_db
from app.models import District, Taluk, Village
from app.services.village_pipeline import normalize_name

logger = logging.getLogger(__name__)

# district -> taluk -> [(village_name, name_ta, lat, lng, place_type)]
DATA: dict[str, dict[str, list[tuple[str, str, float, float, str]]]] = {
    "Villupuram": {
        "Villupuram": [
            ("Villupuram", "விழுப்புரம்", 11.9398, 79.4947, "town"),
            ("Mugaiyur", "முகையூர்", 11.9144, 79.2877, "village"),
            ("Vadakanandhal", "வடகநந்தல்", 11.9481, 79.4719, "village"),
        ],
        "Tindivanam": [
            ("Tindivanam", "திண்டிவனம்", 12.2343, 79.6554, "town"),
            ("Koliyanur", "கொளியனூர்", 11.9950, 79.6146, "village"),
        ],
        "Gingee": [
            ("Gingee", "செஞ்சி", 12.2523, 79.4173, "town"),
            ("Vanur", "வானூர்", 12.0025, 79.6638, "town"),
        ],
        "Ulundurpet": [
            ("Ulundurpet", "உளுந்தூர்பேட்டை", 11.6997, 79.3049, "town"),
        ],
        "Tirukoilur": [
            ("Tirukoilur", "திருக்கோவிலூர்", 11.9694, 79.2045, "town"),
        ],
        "Marakkanam": [
            ("Marakkanam", "மரக்காணம்", 12.2062, 79.9488, "town"),
        ],
        "Vikravandi": [
            ("Vikravandi", "விக்கிரவாண்டி", 12.0345, 79.5440, "town"),
        ],
    },
    "Chennai": {
        "Egmore": [("Chennai", "சென்னை", 13.0827, 80.2707, "city")],
    },
    "Madurai": {
        "Madurai North": [("Madurai", "மதுரை", 9.9252, 78.1198, "city")],
    },
    "Coimbatore": {
        "Coimbatore North": [("Coimbatore", "கோயம்புத்தூர்", 11.0168, 76.9558, "city")],
    },
    "Tiruchirappalli": {
        "Tiruchirappalli West": [("Tiruchirappalli", "திருச்சிராப்பள்ளி", 10.7905, 78.7047, "city")],
    },
    "Salem": {
        "Salem": [("Salem", "சேலம்", 11.6643, 78.1460, "city")],
    },
    "Thanjavur": {
        "Thanjavur": [
            ("Thanjavur", "தஞ்சாவூர்", 10.7870, 79.1378, "city"),
            ("Kumbakonam", "கும்பகோணம்", 10.9602, 79.3845, "town"),
        ],
    },
    "Vellore": {
        "Vellore": [("Vellore", "வேலூர்", 12.9165, 79.1325, "city")],
    },
    "Kanchipuram": {
        "Kanchipuram": [("Kanchipuram", "காஞ்சிபுரம்", 12.8352, 79.7049, "city")],
    },
    "Erode": {
        "Erode": [("Erode", "ஈரோடு", 11.3410, 77.7172, "city")],
    },
}


async def seed(db: AsyncSession) -> None:
    created_villages = 0
    for district_name, taluks in DATA.items():
        district = await db.scalar(select(District).where(District.name == district_name))
        if district is None:
            district = District(name=district_name)
            db.add(district)
            await db.flush()

        for taluk_name, villages in taluks.items():
            taluk = await db.scalar(
                select(Taluk).where(
                    Taluk.district_id == district.id, Taluk.name == taluk_name
                )
            )
            if taluk is None:
                taluk = Taluk(district_id=district.id, name=taluk_name)
                db.add(taluk)
                await db.flush()

            for name, name_ta, lat, lng, place_type in villages:
                exists = await db.scalar(
                    select(Village).where(
                        Village.taluk_id == taluk.id,
                        Village.name_normalized == normalize_name(name),
                    )
                )
                if exists is not None:
                    continue
                db.add(
                    Village(
                        district_id=district.id,
                        taluk_id=taluk.id,
                        name=name,
                        name_normalized=normalize_name(name),
                        name_ta=name_ta,
                        lat=lat,
                        lng=lng,
                        has_coords=True,
                        place_type=place_type,
                        source="demo",
                    )
                )
                created_villages += 1
    await db.commit()
    logger.info("Seed complete: %s new villages", created_villages)


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
