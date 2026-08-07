"""Driver endpoints: bus registration, route building/assignment."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.api.errors import BadRequestError, ConflictError, NotFoundError
from app.deps import CurrentDriver, DbSession
from app.models import Bus, Driver, Route, Village
from app.schemas import BusOut, BusRegisterRequest, RouteOut
from app.services.route_service import build_route

router = APIRouter(prefix="/driver", tags=["driver"])


@router.post("/buses", response_model=BusOut, summary="Register a bus for verification")
async def register_bus(
    body: BusRegisterRequest, db: DbSession, driver: CurrentDriver
) -> Bus:
    existing = await db.scalar(
        select(Bus).where(
            and_(
                Bus.bus_number == body.bus_number,
                Bus.rto_number == body.rto_number,
            )
        )
    )
    if existing is not None:
        raise ConflictError("This bus is already registered.")
    bus = Bus(
        driver_id=driver.id,
        bus_number=body.bus_number.strip().upper(),
        bus_name=body.bus_name.strip() if body.bus_name else None,
        bus_type=body.bus_type,
        rto_number=body.rto_number.strip().upper(),
        verification_status="pending",
    )
    db.add(bus)
    await db.commit()
    await db.refresh(bus)
    return bus


@router.get("/buses", response_model=list[BusOut])
async def my_buses(db: DbSession, driver: CurrentDriver) -> list[Bus]:
    buses = (
        await db.execute(
            select(Bus).where(Bus.driver_id == driver.id).options(selectinload(Bus.route))
        )
    ).scalars().all()
    return list(buses)


@router.post(
    "/routes/build",
    response_model=RouteOut,
    summary="Build (or reuse) a route from start to end village",
)
async def build_route_endpoint(
    body: dict,
    db: DbSession,
    driver: CurrentDriver,
) -> Route:
    district_id = body.get("district_id")
    from_village_id = body.get("from_village_id")
    to_village_id = body.get("to_village_id")
    if not district_id or not from_village_id or not to_village_id:
        raise BadRequestError("district_id, from_village_id and to_village_id are required")

    from_village = await db.get(Village, from_village_id)
    to_village = await db.get(Village, to_village_id)
    if from_village is None or to_village is None:
        raise NotFoundError("Village not found")
    if from_village.district_id != district_id or to_village.district_id != district_id:
        raise BadRequestError("Both villages must belong to the selected district")

    result = await build_route(
        db, district_id=int(district_id), from_village=from_village, to_village=to_village
    )
    return result.route


@router.post(
    "/buses/{bus_id}/assign-route",
    summary="Assign an existing route to one of the driver's buses",
)
async def assign_route(
    bus_id: int,
    body: dict,
    db: DbSession,
    driver: CurrentDriver,
) -> dict:
    route_id = body.get("route_id")
    bus = await db.get(Bus, bus_id)
    if bus is None or bus.driver_id != driver.id:
        raise NotFoundError("Bus not found")
    route = await db.get(Route, route_id)
    if route is None:
        raise NotFoundError("Route not found")
    bus.route_id = route.id
    await db.commit()
    return {"ok": True, "data": {"bus_id": bus.id, "route_id": route.id}}


@router.get("/routes", summary="Routes available in the driver's district")
async def list_routes(
    district_id: int, db: DbSession, driver: CurrentDriver
) -> list[dict]:
    routes = (
        await db.execute(
            select(Route)
            .where(Route.district_id == district_id)
            .order_by(Route.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "from_village_id": r.from_village_id,
            "to_village_id": r.to_village_id,
            "distance_m": r.distance_m,
            "status": r.status,
        }
        for r in routes
    ]
