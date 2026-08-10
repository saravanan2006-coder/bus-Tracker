"""Public (guest) API: districts, villages, route search, live bus tracking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError
from app.deps import DbSession, Tracking
from app.models import (
    AlertSubscription,
    Bus,
    District,
    Favorite,
    LocationPoint,
    Route,
    Taluk,
    Village,
)
from app.schemas import (
    AlertSubscribeRequest,
    DistrictOut,
    FavoriteCreate,
    RouteOut,
    TalukOut,
    VillageOut,
)
from app.services import search_service
from app.services.eta_service import compute_eta
from app.services.geo import project_point_on_polyline

router = APIRouter(tags=["public"])

TRAIL_MINUTES = 30


# --------------------------------------------------------------------- #
# Districts / taluks / villages
# --------------------------------------------------------------------- #
@router.get("/districts", response_model=list[DistrictOut])
async def list_districts(db: DbSession) -> list[dict]:
    rows = (
        await db.execute(
            select(
                District,
                func.count(func.distinct(Taluk.id)).label("taluks"),
                func.count(func.distinct(Village.id)).label("villages"),
            )
            .outerjoin(Taluk, Taluk.district_id == District.id)
            .outerjoin(Village, Village.district_id == District.id)
            .where(District.is_active.is_(True))
            .group_by(District.id)
            .order_by(District.name)
        )
    ).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "name_ta": d.name_ta,
            "taluk_count": taluks,
            "village_count": villages,
        }
        for d, taluks, villages in rows
    ]


@router.get("/districts/{district_id}/taluks", response_model=list[TalukOut])
async def list_taluks(district_id: int, db: DbSession) -> list[Taluk]:
    return list(
        (
            await db.execute(
                select(Taluk)
                .where(and_(Taluk.district_id == district_id, Taluk.is_active.is_(True)))
                .order_by(Taluk.name)
            )
        ).scalars().all()
    )


@router.get(
    "/districts/{district_id}/villages",
    response_model=list[VillageOut],
)
async def list_villages(
    district_id: int,
    db: DbSession,
    q: str | None = None,
    taluk_id: int | None = None,
    limit: int = 100,
) -> list[Village]:
    if q:
        return await search_service.search_villages(
            db, district_id, q=q, taluk_id=taluk_id, limit=min(limit, 200)
        )
    stmt = select(Village).where(Village.district_id == district_id)
    if taluk_id:
        stmt = stmt.where(Village.taluk_id == taluk_id)
    return list(
        (await db.execute(stmt.order_by(Village.name).limit(min(limit, 500)))).scalars().all()
    )


# --------------------------------------------------------------------- #
# Route search
# --------------------------------------------------------------------- #
@router.get("/routes/find", summary="Find routes connecting two villages")
async def find_routes(
    district_id: int,
    from_village_id: int,
    to_village_id: int,
    db: DbSession,
    tracking: Tracking,
) -> dict:
    routes = await search_service.find_routes_for_pair(
        db, district_id, from_village_id, to_village_id
    )
    results = []
    for route in routes:
        buses = await search_service.active_buses_for_route(db, route.id)
        bus_payloads = []
        for bus in buses:
            bus_payloads.append(await search_service.assemble_bus_detail(db, bus, tracking))
        results.append(
            {
                "route": RouteOut.model_validate(route),
                "buses": bus_payloads,
            }
        )
    return {"ok": True, "data": results}


@router.get("/routes/{route_id}", response_model=RouteOut)
async def get_route(route_id: int, db: DbSession) -> Route:
    route = await db.get(Route, route_id)
    if route is None:
        raise NotFoundError("Route not found")
    return route


# --------------------------------------------------------------------- #
# Bus lookup
# --------------------------------------------------------------------- #
@router.get("/buses/search", summary="Search buses by route number or private name")
async def search_buses(db: DbSession, q: str) -> dict:
    term = q.strip().lower()
    buses = (
        await db.execute(
            select(Bus)
            .where(
                and_(
                    Bus.is_active.is_(True),
                    or_(
                        func.lower(Bus.bus_number).like(f"%{term}%"),
                        func.lower(Bus.bus_name).like(f"%{term}%"),
                    ),
                )
            )
            .options(selectinload(Bus.route).selectinload(Route.stops))
            .limit(20)
        )
    ).scalars().all()
    return {
        "ok": True,
        "data": [
            {
                "id": b.id,
                "bus_number": b.bus_number,
                "bus_name": b.bus_name,
                "bus_type": b.bus_type,
                "verified": b.verification_status == "approved",
            }
            for b in buses
        ],
    }


@router.get("/buses/{bus_id}", summary="Full live detail for one bus")
async def bus_detail(bus_id: int, db: DbSession, tracking: Tracking) -> dict:
    bus = await db.get(
        Bus, bus_id, options=[selectinload(Bus.route).selectinload(Route.stops)]
    )
    if bus is None:
        raise NotFoundError("Bus not found")
    return {"ok": True, "data": await search_service.assemble_bus_detail(db, bus, tracking)}


@router.get("/buses/{bus_id}/history", summary="Recent GPS trail for a bus")
async def bus_history(
    bus_id: int,
    db: DbSession,
    minutes: int = TRAIL_MINUTES,
    limit: int = 500,
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(minutes=min(minutes, 180))
    points = (
        await db.execute(
            select(LocationPoint)
            .where(
                and_(
                    LocationPoint.bus_id == bus_id,
                    LocationPoint.ts >= since,
                    LocationPoint.is_anomalous.is_(False),
                )
            )
            .order_by(LocationPoint.ts.desc())
            .limit(min(limit, 1000))
        )
    ).scalars().all()
    trail = [
        {"lat": p.lat, "lng": p.lng, "ts": p.ts.isoformat(), "speed_kmh": p.speed_kmh}
        for p in reversed(points)
    ]
    return {"ok": True, "data": {"bus_id": bus_id, "trail": trail}}


# --------------------------------------------------------------------- #
# Favorites (guest, keyed by anonymous device id)
# --------------------------------------------------------------------- #
@router.post("/favorites", summary="Save a favourite village pair for a device")
async def add_favorite(body: FavoriteCreate, db: DbSession) -> dict:
    fav = Favorite(
        device_id=body.device_id,
        from_village_id=body.from_village_id,
        to_village_id=body.to_village_id,
    )
    db.add(fav)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001 - duplicate favourite is a no-op.
        await db.rollback()
    return {"ok": True, "data": {"saved": True}}


@router.get("/favorites", summary="List favourites for a device")
async def list_favorites(db: DbSession, device_id: str) -> dict:
    favs = (
        await db.execute(
            select(Favorite).where(Favorite.device_id == device_id)
        )
    ).scalars().all()
    from_ids = {f.from_village_id for f in favs} | {f.to_village_id for f in favs}
    villages = {
        v.id: search_service._village_summary(v)
        for v in (
            await db.execute(select(Village).where(Village.id.in_(from_ids)))
        ).scalars()
    }
    return {
        "ok": True,
        "data": [
            {
                "id": f.id,
                "from_village_id": f.from_village_id,
                "to_village_id": f.to_village_id,
                "from_village": villages.get(f.from_village_id),
                "to_village": villages.get(f.to_village_id),
            }
            for f in favs
        ],
    }


@router.delete("/favorites/{favorite_id}", summary="Delete a favourite")
async def delete_favorite(favorite_id: int, db: DbSession, device_id: str) -> dict:
    fav = await db.get(Favorite, favorite_id)
    if fav is None or fav.device_id != device_id:
        raise NotFoundError("Favourite not found")
    await db.delete(fav)
    await db.commit()
    return {"ok": True, "data": {"deleted": True}}


# --------------------------------------------------------------------- #
# Push alerts
# --------------------------------------------------------------------- #
@router.post("/alerts", summary="Subscribe to an approaching-bus alert")
async def subscribe_alert(body: AlertSubscribeRequest, db: DbSession) -> dict:
    sub = AlertSubscription(
        device_id=body.device_id,
        bus_id=body.bus_id,
        stop_village_id=body.stop_village_id,
        fcm_token=body.fcm_token,
        distance_m=body.distance_m,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {"ok": True, "data": {"subscription_id": sub.id}}
