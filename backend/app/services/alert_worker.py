"""Background worker that turns alert subscriptions into push notifications.

For every subscription, whenever the subscribed bus's live position gets
within `distance_m` of the requested stop, the worker sends a push (via the
configured PushSender) and marks the subscription `triggered`. Once the bus
moves beyond the radius again the subscription re-arms, so each approach
produces exactly one notification.

Like the demo bus simulator, the worker runs as an asyncio task inside the
backend process so it shares the in-process memory store with the REST/WS
layer (live positions live there when Redis is not configured).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.redis_client import get_store
from app.core.pubsub import get_broker
from app.models import AlertSubscription, Bus, Route, RouteStop, Village
from app.services.geo import haversine, point_at_fraction
from app.services.push_service import PushSender, build_sender
from app.services.tracking_service import TrackingService

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 10.0

_SUB_LOAD = selectinload(AlertSubscription.bus).selectinload(Bus.route)


async def _stop_point(
    db: AsyncSession, route: Route, stop_village_id: int
) -> tuple[float, float] | None:
    """Coordinates on the route geometry that correspond to a stop village.

    Prefers the stop's position on the route polyline (accurate for arrival
    distance); falls back to the village centre when the village is not a
    stop on this bus's route.
    """
    stop = await db.scalar(
        select(RouteStop).where(
            RouteStop.route_id == route.id, RouteStop.village_id == stop_village_id
        )
    )
    if stop is not None:
        try:
            return point_at_fraction(route.polyline, stop.progress)
        except ValueError:
            pass
    village = await db.get(Village, stop_village_id)
    if village is None or not village.has_coords:
        return None
    return (village.lat, village.lng)  # type: ignore[return-value]


async def _distance_to_stop(
    db: AsyncSession, live: dict, bus: Bus, stop_village_id: int
) -> float | None:
    """Great-circle distance (m) from the bus to the requested stop."""
    if bus.route_id is None:
        return None
    route = await db.get(Route, bus.route_id)
    if route is None:
        return None
    target = await _stop_point(db, route, stop_village_id)
    if target is None:
        return None
    return haversine((float(live["lat"]), float(live["lng"])), target)


async def alert_worker_tick(
    db: AsyncSession, sender: PushSender, tracking: TrackingService
) -> dict[str, int]:
    """Scan all subscriptions once; return counts of what happened."""
    subs = (
        (
            await db.execute(
                select(AlertSubscription)
                .options(_SUB_LOAD)
                .where(AlertSubscription.fcm_token.is_not(None))
            )
        )
        .scalars()
        .all()
    )

    live_cache: dict[int, dict] = {}
    fired = 0
    rearmed = 0
    skipped = 0
    for sub in subs:
        if sub.bus is None:
            skipped += 1
            continue
        live = live_cache.get(sub.bus_id)
        if live is None:
            live = await tracking.get_live_position(sub.bus_id)
            if live is None:
                skipped += 1
                continue
            live_cache[sub.bus_id] = live
        if live.get("stale"):
            skipped += 1
            continue

        distance = await _distance_to_stop(db, live, sub.bus, sub.stop_village_id)
        if distance is None:
            skipped += 1
            continue

        within = distance <= sub.distance_m
        token = sub.fcm_token
        if within and not sub.triggered:
            if token is None:
                skipped += 1
                continue
            sent = await sender.send(
                token=token,
                title=f"{sub.bus.bus_number} approaching your stop",
                body=(
                    f"{sub.bus.bus_name or sub.bus.bus_number} is "
                    f"{int(distance)} m away."
                ),
                data={
                    "bus_id": str(sub.bus.id),
                    "trip_id": str(live.get("trip_id") or ""),
                    "stop_village_id": str(sub.stop_village_id),
                },
            )
            if sent:
                sub.triggered = True
                fired += 1
        elif not within and sub.triggered:
            sub.triggered = False
            rearmed += 1
    await db.commit()
    return {"scanned": len(subs), "fired": fired, "rearmed": rearmed, "skipped": skipped}


async def run_alert_worker() -> None:
    """Poll subscriptions forever (intended as an in-process background task)."""
    from app.database import SessionLocal, init_db

    await init_db()
    store = await get_store()
    broker = await get_broker()
    tracking = TrackingService(store, broker)
    sender = build_sender()
    logger.info("Alert worker running (sender=%s)", type(sender).__name__)
    while True:
        try:
            async with SessionLocal() as db:
                result = await alert_worker_tick(db, sender, tracking)
            if result["scanned"]:
                logger.info("alert tick: %s", result)
        except Exception:  # noqa: BLE001 - keep polling through transient errors
            logger.exception("alert worker tick failed")
        await asyncio.sleep(POLL_INTERVAL_S)
