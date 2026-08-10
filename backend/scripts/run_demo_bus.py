"""Demo driver simulator: one bus loops the Tindivanam -> Gingee route.

Creates a demo driver + approved bus (idempotent), builds the route through
OSRM, starts an active trip, and feeds GPS pings along the polyline. Pings
carry fast-forwarded timestamps so the ~30 km route plays out in about a
minute instead of 40 minutes; the implied speed stays realistic so nothing
is flagged anomalous. Loops forever until killed.

Usage:
    DATABASE_URL=sqlite+aiosqlite:////tmp/bustracker_demo.db \
        python -m scripts.run_demo_bus
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.pubsub import get_broker
from app.core.redis_client import get_store
from app.database import SessionLocal, init_db
from app.models import Bus, District, Driver, Trip, Village
from app.services.geo import polyline_length
from app.services.route_service import build_route
from app.services.tracking_service import TrackingService

logger = logging.getLogger(__name__)

DEMO_PHONE = "+919876500000"
DEMO_NAME = "Demo Driver"
BUS_NUMBER = "TN32 9999"
RTO = "TN32Z9999"
BUS_NAME = "Villupuram Express"
FROM = "Tindivanam"
TO = "Gingee"
SPEED_KMH = 50.0
PING_INTERVAL_S = 2.0
# Each ping advances the simulated clock by this much (minutes of travel).
TIME_STEP_S = 60.0


def _heading(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    return math.degrees(math.atan2(dlng * math.cos(math.radians(lat1)), dlat))


async def _ensure_driver_bus(db):
    driver = await db.scalar(select(Driver).where(Driver.phone == DEMO_PHONE))
    if driver is None:
        driver = Driver(phone=DEMO_PHONE, name=DEMO_NAME, language="ta")
        db.add(driver)
        await db.flush()
    bus = await db.scalar(select(Bus).where(Bus.bus_number == BUS_NUMBER))
    if bus is None:
        bus = Bus(
            driver_id=driver.id,
            bus_number=BUS_NUMBER,
            rto_number=RTO,
            bus_name=BUS_NAME,
            bus_type="govt",
            verification_status="approved",
            is_active=True,
        )
        db.add(bus)
        await db.flush()
    return driver, bus


async def run_demo_loop() -> None:
    """Simulate one bus looping Tindivanam -> Gingee.

    Runs forever. Intended to be launched as an asyncio task inside the
    backend process so the in-process memory broker/store are shared with the
    WebSocket/REST layer (a separate process would never reach clients).
    """
    await init_db()
    store = await get_store()
    broker = await get_broker()
    tracking = TrackingService(store, broker)

    async with SessionLocal() as db:
        district = await db.scalar(
            select(District).where(District.name == "Villupuram")
        )
        if district is None:
            raise SystemExit("District Villupuram not found in the database")
        fv = await db.scalar(
            select(Village).where(
                Village.district_id == district.id, Village.name == FROM
            )
        )
        tv = await db.scalar(
            select(Village).where(
                Village.district_id == district.id, Village.name == TO
            )
        )
        if fv is None or tv is None:
            raise SystemExit(f"Villages {FROM}/{TO} not found in {district.name}")
        if not fv.has_coords or not tv.has_coords:
            raise SystemExit("Demo villages lack coordinates; cannot route")

        driver, bus = await _ensure_driver_bus(db)
        result = await build_route(db, district.id, fv, tv)
        route = result.route
        bus.route_id = route.id

        # Clear any stale active trip for this bus, then start fresh.
        stale = await db.scalar(
            select(Trip).where(Trip.bus_id == bus.id, Trip.status == "active")
        )
        if stale is not None:
            stale.status = "ended"
            stale.ended_at = datetime.now(timezone.utc)
        trip = Trip(
            driver_id=driver.id,
            bus_id=bus.id,
            route_id=route.id,
            status="active",
        )
        db.add(trip)
        await db.commit()
        await db.refresh(trip)
        logger.info(
            "Trip %s active: bus %s on %s -> %s (route %s, %.1f km)",
            trip.id,
            bus.bus_number,
            FROM,
            TO,
            route.id,
            (route.distance_m or polyline_length(route.polyline)) / 1000.0,
        )

        poly = route.polyline
        n = len(poly)
        cumulative = [0.0]
        for i in range(n - 1):
            from app.services.geo import haversine

            cumulative.append(
                cumulative[-1] + haversine(poly[i], poly[i + 1])
            )
        total_m = cumulative[-1]
        step_m = SPEED_KMH / 3.6 * TIME_STEP_S
        meters = 0.0
        sim_ts = datetime.now(timezone.utc)

        logger.info("Simulating bus %s (realtime x%d)", bus.bus_number, int(TIME_STEP_S / PING_INTERVAL_S))
        while True:
            idx = 0
            while idx < n - 1 and cumulative[idx + 1] <= meters:
                idx += 1
            seg = cumulative[idx + 1] - cumulative[idx]
            frac = 0.0 if seg <= 0 else (meters - cumulative[idx]) / seg
            lat = poly[idx][0] + (poly[idx + 1][0] - poly[idx][0]) * frac
            lng = poly[idx][1] + (poly[idx + 1][1] - poly[idx][1]) * frac
            heading = _heading(poly[idx][0], poly[idx][1], poly[idx + 1][0], poly[idx + 1][1])

            sim_ts += timedelta(seconds=TIME_STEP_S)
            await tracking.ingest(
                db, trip, lat, lng, SPEED_KMH, heading, ts=sim_ts
            )

            meters += step_m
            if meters > total_m:
                meters = 0.0
                logger.info("Lap complete — restarting route")
            await asyncio.sleep(PING_INTERVAL_S)


async def main() -> None:
    """Standalone entrypoint (also launched in-process via RUN_DEMO_BUS=1)."""
    logging.basicConfig(level=logging.INFO)
    await run_demo_loop()


if __name__ == "__main__":
    asyncio.run(main())
