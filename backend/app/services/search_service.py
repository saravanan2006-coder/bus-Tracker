"""Public search: village pickers, route matching, live bus details."""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Bus,
    Route,
    RouteStop,
    Trip,
    Village,
)
from app.services import eta_service
from app.services.geo import project_point_on_polyline
from app.services.tracking_service import TrackingService

# Searching within a taluk is a small list; but name ILIKE needs an index
# on the normalized column for production scale (see migrations).


async def search_villages(
    db: AsyncSession,
    district_id: int,
    q: str | None = None,
    taluk_id: int | None = None,
    limit: int = 50,
) -> list[Village]:
    stmt = select(Village).where(Village.district_id == district_id)
    if taluk_id:
        stmt = stmt.where(Village.taluk_id == taluk_id)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Village.name.ilike(term),
                Village.name_normalized.ilike(term),
                Village.name_ta.ilike(term),
            )
        )
    return list(
        (
            await db.execute(
                stmt.order_by(Village.name).limit(limit)
            )
        ).scalars().all()
    )


async def find_routes_for_pair(
    db: AsyncSession,
    district_id: int,
    from_village_id: int,
    to_village_id: int,
) -> list[Route]:
    """Routes where the from-village and to-village both lie on the path.

    A route is only returned when travel is possible in the correct
    direction (to-village progress strictly ahead of from-village).
    """
    routes = (
        await db.execute(
            select(Route)
            .where(
                and_(
                    Route.district_id == district_id,
                    Route.status.in_(("active", "unverified")),
                )
            )
            .options(selectinload(Route.stops))
        )
    ).scalars().all()

    candidates: list[Route] = []
    for route in routes:
        stops = {s.village_id: s.progress for s in route.stops}
        from_progress = stops.get(from_village_id)
        to_progress = stops.get(to_village_id)
        if (
            from_progress is not None
            and to_progress is not None
            and to_progress > from_progress
        ):
            candidates.append(route)
    return candidates


async def active_buses_for_route(
    db: AsyncSession, route_id: int
) -> list[Bus]:
    """Buses currently on an active trip for the given route."""
    active_bus_ids = select(Trip.bus_id).where(
        and_(Trip.route_id == route_id, Trip.status == "active")
    )
    return list(
        (
            await db.execute(
                select(Bus).where(
                    and_(
                        Bus.route_id == route_id,
                        Bus.is_active.is_(True),
                        Bus.id.in_(active_bus_ids),
                    )
                )
            )
        ).scalars().all()
    )


async def assemble_bus_detail(
    db: AsyncSession,
    bus: Bus,
    tracking: TrackingService,
) -> dict[str, Any]:
    """Full public payload for a bus: identity, route, live position, ETA."""
    live = await tracking.get_live_position(bus.id)
    route_payload: dict | None = None
    if bus.route:
        route_payload = {
            "id": bus.route.id,
            "from_village": _village_summary(await db.get(Village, bus.route.from_village_id)),
            "to_village": _village_summary(await db.get(Village, bus.route.to_village_id)),
            "distance_m": bus.route.distance_m,
            "stops": [
                {
                    "village_id": stop.village_id,
                    "seq": stop.seq,
                    "progress": stop.progress,
                    "village": _village_summary(await db.get(Village, stop.village_id)),
                }
                for stop in sorted(bus.route.stops, key=lambda s: s.seq)
            ],
        }

    eta: dict | None = None
    if live and bus.route:
        try:
            eta = await eta_service.compute_eta(db, tracking._store, bus.id, bus.route, live)
        except Exception:  # noqa: BLE001 - ETA is best-effort.
            eta = None

    return {
        "id": bus.id,
        "bus_number": bus.bus_number,
        "bus_name": bus.bus_name,
        "bus_type": bus.bus_type,
        "rto_number": bus.rto_number,
        "verified": bus.verification_status == "approved",
        "route": route_payload,
        "live": live,
        "eta": eta,
    }


def _village_summary(village: Village | None) -> dict | None:
    if village is None:
        return None
    return {
        "id": village.id,
        "name": village.name,
        "name_ta": village.name_ta,
        "taluk_id": village.taluk_id,
    }
