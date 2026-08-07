"""ETA computation: live progress + blended historical/live speed, cached."""
from __future__ import annotations

import asyncio
import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_client import KeyValueStore
from app.models import LocationPoint, Route, RouteStop, Village
from app.services.geo import project_point_on_polyline

DEFAULT_SPEED_KMH = 30.0
MIN_HISTORY_SPEED_KMH = 5.0
MAX_HISTORY_SPEED_KMH = 90.0
HISTORY_LOOKBACK_DAYS = 14
MIN_HISTORY_SAMPLES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def eta_cache_key(bus_id: int) -> str:
    return f"bus:{bus_id}:eta"


async def historical_median_speed(db: AsyncSession, route_id: int) -> float | None:
    """Median recorded speed for a route over the lookback window."""
    since = _now() - timedelta(days=HISTORY_LOOKBACK_DAYS)
    rows = (
        await db.execute(
            select(LocationPoint.speed_kmh).where(
                LocationPoint.route_id == route_id,
                LocationPoint.speed_kmh.is_not(None),
                LocationPoint.speed_kmh >= MIN_HISTORY_SPEED_KMH,
                LocationPoint.speed_kmh <= MAX_HISTORY_SPEED_KMH,
                LocationPoint.is_anomalous.is_(False),
                LocationPoint.ts >= since,
            )
        )
    ).scalars().all()
    if len(rows) < MIN_HISTORY_SAMPLES:
        return None
    return float(statistics.median(rows))


def _blend_speed(historical: float | None, live: float | None) -> float:
    """Weighted blend: live speed dominates; history fills the gaps."""
    if live is None or live <= 0:
        return historical or DEFAULT_SPEED_KMH
    if historical is None:
        return max(live, 8.0)
    # 60/40 live vs historical is robust to jitter.
    return 0.6 * live + 0.4 * historical


async def compute_eta(
    db: AsyncSession,
    store: KeyValueStore,
    bus_id: int,
    route: Route,
    live: dict[str, Any],
) -> dict[str, Any]:
    """Compute ETA from a live position payload, with Redis caching."""
    cached = await store.get(eta_cache_key(bus_id))
    if cached is not None:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    progress, distance_along, _, _ = project_point_on_polyline(
        (float(live["lat"]), float(live["lng"])), route.polyline
    )
    distance_remaining_m = max(0.0, (1.0 - progress) * (route.distance_m or 0.0))

    historical, live_speed = (
        await historical_median_speed(db, route.id),
        (float(live["speed_kmh"]) if live.get("speed_kmh") is not None else None),
    )
    speed_kmh = _blend_speed(historical, live_speed)
    eta_minutes = (
        distance_remaining_m / 1000.0 / speed_kmh * 60.0 if speed_kmh > 0 else 0.0
    )

    stops = (
        await db.execute(
            select(RouteStop).where(RouteStop.route_id == route.id)
        )
    ).scalars().all()
    next_stop = None
    for stop in sorted(stops, key=lambda s: s.progress):
        if stop.progress > progress + 0.001:
            stop_eta = (
                (stop.progress - progress) * (route.distance_m or 0.0)
                / 1000.0
                / speed_kmh
                * 60.0
                if speed_kmh > 0
                else 0.0
            )
            village = await db.get(Village, stop.village_id)
            next_stop = {
                "village_id": stop.village_id,
                "seq": stop.seq,
                "progress": stop.progress,
                "eta_minutes": round(stop_eta, 1),
                "village": (
                    {
                        "id": village.id,
                        "name": village.name,
                        "name_ta": village.name_ta,
                        "taluk_id": village.taluk_id,
                    }
                    if village is not None
                    else None
                ),
            }
            break

    result = {
        "progress": round(progress, 4),
        "distance_remaining_m": round(distance_remaining_m, 1),
        "eta_minutes": round(eta_minutes, 1),
        "predicted_speed_kmh": round(speed_kmh, 1),
        "next_stop": next_stop,
        "computed_at": _now().isoformat(),
    }
    await store.set(eta_cache_key(bus_id), json.dumps(result, ensure_ascii=False), ex=settings.redis_eta_ttl_seconds)
    return result
