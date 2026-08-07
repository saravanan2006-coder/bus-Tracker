"""Trip endpoints: start/end trips and location streaming (rate-limited)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import and_, select

from app.api.errors import BadRequestError, NotFoundError, RateLimitedError
from app.config import settings
from app.core.rate_limit import RateLimiter
from app.deps import CurrentDriver, DbSession, Store, Tracking
from app.models import Bus, Route, Trip
from app.schemas import LocationUpdate, TripOut

router = APIRouter(prefix="/driver/trips", tags=["trips"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", response_model=TripOut, summary="Start sharing a trip")
async def start_trip(
    body: dict, db: DbSession, driver: CurrentDriver, tracking: Tracking
) -> Trip:
    bus_id, route_id = body.get("bus_id"), body.get("route_id")
    if not bus_id or not route_id:
        raise BadRequestError("bus_id and route_id are required")

    bus = await db.get(Bus, bus_id)
    if bus is None or bus.driver_id != driver.id:
        raise NotFoundError("Bus not found")

    route = await db.get(Route, route_id)
    if route is None:
        raise NotFoundError("Route not found")
    if bus.route_id != route.id:
        raise BadRequestError("Bus is not assigned to this route")

    active = await tracking.has_active_trip(db, driver.id)
    if active is not None:
        raise BadRequestError("An active trip is already running for this driver")

    trip = Trip(driver_id=driver.id, bus_id=bus.id, route_id=route_id, status="active")
    db.add(trip)
    await db.commit()
    await db.refresh(trip)
    return trip


@router.get("/active", summary="The driver's currently active trip, if any")
async def active_trip(db: DbSession, driver: CurrentDriver, tracking: Tracking) -> dict:
    trip = await tracking.has_active_trip(db, driver.id)
    if trip is None:
        return {"ok": True, "data": None}
    return {"ok": True, "data": TripOut.model_validate(trip)}


@router.post(
    "/{trip_id}/location",
    summary="Stream a GPS fix for an active trip",
    status_code=202,
)
async def share_location(
    trip_id: int,
    body: LocationUpdate,
    db: DbSession,
    driver: CurrentDriver,
    tracking: Tracking,
    store: Store,
) -> dict:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.driver_id != driver.id:
        raise NotFoundError("Trip not found")
    if trip.status != "active":
        raise BadRequestError("Trip is not active")

    # Per-driver rate limit protects the ingest pipeline from abusive clients.
    limiter = RateLimiter(
        store,
        limit=settings.max_location_rate_per_second,
        window_seconds=1,
    )
    if not await limiter.allow(f"loc:{driver.id}"):
        raise RateLimitedError("Location updates too frequent")

    result = await tracking.ingest(
        db,
        trip,
        body.lat,
        body.lng,
        body.speed_kmh,
        body.heading,
        body.ts,
    )
    if not result.accepted:
        raise BadRequestError(f"Location rejected: {result.reason}")
    return {
        "ok": True,
        "data": {
            "accepted": True,
            "anomalous": result.reason == "anomalous",
            "ts": body.ts or _now().isoformat(),
        },
    }


@router.post("/{trip_id}/end", summary="End an active trip")
async def end_trip(
    trip_id: int, db: DbSession, driver: CurrentDriver, tracking: Tracking
) -> dict:
    trip = await db.get(Trip, trip_id)
    if trip is None or trip.driver_id != driver.id:
        raise NotFoundError("Trip not found")
    if trip.status != "active":
        raise BadRequestError("Trip is not active")
    await tracking.end_trip(db, trip)
    return {"ok": True, "data": {"trip_id": trip.id, "status": "ended"}}
