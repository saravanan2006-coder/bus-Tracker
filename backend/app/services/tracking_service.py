"""Trip tracking: location ingest, anomaly checks, staleness and live fan-out."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.pubsub import PubSubBroker
from app.core.redis_client import KeyValueStore
from app.models import Bus, LocationPoint, Route, Trip
from app.services.geo import Point, project_point_on_polyline, speed_between


def _now() -> datetime:
    return datetime.now(timezone.utc)


def bus_channel(bus_id: int) -> str:
    return f"bus:{bus_id}"


def bus_position_key(bus_id: int) -> str:
    return f"bus:{bus_id}:pos"


@dataclass
class IngestResult:
    accepted: bool
    point: LocationPoint | None = None
    reason: str | None = None


class TrackingService:
    def __init__(self, store: KeyValueStore, broker: PubSubBroker) -> None:
        self._store = store
        self._broker = broker

    # ------------------------------------------------------------------ #
    # Hot state
    # ------------------------------------------------------------------ #
    async def get_live_position(self, bus_id: int) -> dict | None:
        raw = await self._store.get(bus_position_key(bus_id))
        if raw is None:
            return None
        import json

        payload = json.loads(raw)
        payload["stale"] = self.is_stale(payload.get("ts"))
        return payload

    @staticmethod
    def is_stale(ts: str | None, now_ts: float | None = None) -> bool:
        if not ts:
            return True
        from datetime import datetime as dt

        try:
            point_ts = dt.fromisoformat(ts).timestamp()
        except ValueError:
            return True
        import time

        if now_ts is None:
            now_ts = time.time()
        return (now_ts - point_ts) > settings.stale_after_seconds

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    async def ingest(
        self,
        db: AsyncSession,
        trip: Trip,
        lat: float,
        lng: float,
        speed_kmh: float | None,
        heading: float | None,
        ts: datetime | None = None,
    ) -> IngestResult:
        ts = ts or _now()

        # Reject obviously out-of-range coordinates.
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return IngestResult(False, reason="invalid_coordinates")

        point: Point = (lat, lng)
        anomalous = False
        off_route_m: float | None = None

        # Anomaly: teleport speed between the last two fixes.
        last_pos = await self.get_live_position(trip.bus_id)
        if last_pos:
            try:
                last_lat = float(last_pos["lat"])
                last_lng = float(last_pos["lng"])
                last_ts = datetime.fromisoformat(last_pos["ts"])
                delta_s = (ts - last_ts).total_seconds()
                if delta_s > 0:
                    impl_speed = speed_between(
                        (last_lat, last_lng), (lat, lng), delta_s
                    )
                    if impl_speed > settings.anomaly_max_speed_kmh:
                        anomalous = True
            except (KeyError, TypeError, ValueError):
                pass

        # Anomaly: far off the assigned route.
        route: Route | None = None
        if trip.route_id:
            route = await db.get(Route, trip.route_id)
        if route is not None:
            from app.services.geo import point_to_polyline_distance

            off_route_m = point_to_polyline_distance(point, route.polyline)
            if off_route_m > settings.anomaly_off_route_threshold_m:
                anomalous = True

        location = LocationPoint(
            trip_id=trip.id,
            bus_id=trip.bus_id,
            route_id=trip.route_id,
            lat=lat,
            lng=lng,
            speed_kmh=speed_kmh,
            heading=heading,
            ts=ts,
            is_anomalous=anomalous,
            off_route_m=off_route_m,
        )
        db.add(location)
        trip.total_points += 1
        await db.commit()

        # Anomalous points are still shown but never treated as definitive.
        await self._publish_live(trip, location, anomalous)
        return IngestResult(True, point=location, reason="anomalous" if anomalous else None)

    async def _publish_live(
        self, trip: Trip, location: LocationPoint, anomalous: bool
    ) -> None:
        payload = {
            "bus_id": trip.bus_id,
            "trip_id": trip.id,
            "lat": location.lat,
            "lng": location.lng,
            "speed_kmh": location.speed_kmh,
            "heading": location.heading,
            "ts": location.ts.isoformat(),
            "anomalous": anomalous,
        }
        # Update hot state (Redis) with a TTL so stale buses auto-expire.
        await self._store.set(
            bus_position_key(trip.bus_id),
            _serialize(payload),
            ex=settings.redis_location_ttl_seconds,
        )
        # Fan out to every subscribed client.
        await self._broker.publish(bus_channel(trip.bus_id), payload)

    # ------------------------------------------------------------------ #
    # Trip lifecycle helpers
    # ------------------------------------------------------------------ #
    async def has_active_trip(self, db: AsyncSession, driver_id: int) -> Trip | None:
        return await db.scalar(
            select(Trip).where(
                and_(
                    Trip.driver_id == driver_id,
                    Trip.status == "active",
                    Trip.ended_at.is_(None),
                )
            )
        )

    async def end_trip(self, db: AsyncSession, trip: Trip) -> None:
        trip.status = "ended"
        trip.ended_at = _now()
        await db.commit()
        await self._store.delete(bus_position_key(trip.bus_id))
        # Broadcast a terminal message so watchers switch to "trip ended".
        await self._broker.publish(
            bus_channel(trip.bus_id),
            {"bus_id": trip.bus_id, "trip_id": trip.id, "ended": True, "ts": _now().isoformat()},
        )


def _serialize(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
