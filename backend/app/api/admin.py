"""Admin endpoints: bus verification, route verification, platform stats.

Authenticated via a static API key header (X-Admin-Key). Replace with a
proper role-based system before production.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select

from app.config import settings
from app.deps import DbSession
from app.models import Bus, District, Driver, Route, Trip, Village

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    # Constant-time comparison avoids a timing side-channel on the key.
    expected = settings.admin_api_key
    if x_admin_key is None or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid admin key"},
        )


@router.get("/buses", dependencies=[Depends(require_admin)])
async def admin_buses(db: DbSession, bstatus: str = "pending") -> dict:
    buses = (
        await db.execute(
            select(Bus).where(Bus.verification_status == bstatus).order_by(Bus.created_at)
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
                "rto_number": b.rto_number,
                "driver_id": b.driver_id,
                "photo_path": b.photo_path,
                "created_at": b.created_at.isoformat(),
            }
            for b in buses
        ],
    }


@router.post("/buses/{bus_id}/approve", dependencies=[Depends(require_admin)])
async def approve_bus(bus_id: int, db: DbSession) -> dict:
    bus = await db.get(Bus, bus_id)
    if bus is None:
        raise HTTPException(status_code=404, detail="Bus not found")
    bus.verification_status = "approved"
    bus.rejected_reason = None
    bus.verified_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "data": {"bus_id": bus.id, "status": "approved"}}


@router.post("/buses/{bus_id}/reject", dependencies=[Depends(require_admin)])
async def reject_bus(bus_id: int, body: dict, db: DbSession) -> dict:
    bus = await db.get(Bus, bus_id)
    if bus is None:
        raise HTTPException(status_code=404, detail="Bus not found")
    bus.verification_status = "rejected"
    bus.rejected_reason = body.get("reason", "Not approved by admin")
    await db.commit()
    return {"ok": True, "data": {"bus_id": bus.id, "status": "rejected"}}


@router.post("/routes/{route_id}/verify", dependencies=[Depends(require_admin)])
async def verify_route(route_id: int, db: DbSession) -> dict:
    route = await db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    route.status = "active"
    await db.commit()
    return {"ok": True, "data": {"route_id": route.id, "status": "active"}}


@router.get("/stats", dependencies=[Depends(require_admin)])
async def stats(db: DbSession) -> dict:
    districts = await db.scalar(select(func.count(District.id)))
    taluks = await db.scalar(select(func.count(func.distinct(Village.taluk_id))))
    villages = await db.scalar(select(func.count(Village.id)))
    buses = await db.scalar(select(func.count(Bus.id)))
    verified_buses = await db.scalar(
        select(func.count(Bus.id)).where(Bus.verification_status == "approved")
    )
    drivers = await db.scalar(select(func.count(Driver.id)))
    routes = await db.scalar(select(func.count(Route.id)))
    active_trips = await db.scalar(
        select(func.count(Trip.id)).where(Trip.status == "active")
    )
    return {
        "ok": True,
        "data": {
            "districts": districts,
            "taluks": taluks,
            "villages": villages,
            "buses": buses,
            "verified_buses": verified_buses,
            "drivers": drivers,
            "routes": routes,
            "active_trips": active_trips,
        },
    }
