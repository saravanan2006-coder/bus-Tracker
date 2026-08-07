"""Test fixtures: isolated SQLite database + FastAPI test client."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_bustracker.db")
os.environ["REDIS_ENABLED"] = "false"
os.environ["DEBUG"] = "false"
os.environ["ENVIRONMENT"] = "test"

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import select

from app.database import SessionLocal, engine, init_db
from app.models import Bus, District, Driver, Village

DB_FILE = "test_bustracker.db"


async def _fresh_database():
    """Recreate an empty, seeded database for each test."""
    await engine.dispose()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    await init_db()

    from app.seed.demo_data import seed

    async with SessionLocal() as session:
        await seed(session)


@pytest_asyncio.fixture(autouse=True)
async def _database():
    await _fresh_database()
    yield
    await engine.dispose()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


@pytest_asyncio.fixture(autouse=True)
async def _isolated_runtime(_database):
    """Reset cached Redis/store/broker singletons so state never leaks
    between tests (rate-limit counters, live positions, pub/sub channels)."""
    from app.core import pubsub, redis_client

    await redis_client.reset_runtime()
    await pubsub.reset_runtime()
    yield
    await redis_client.reset_runtime()
    await pubsub.reset_runtime()


@pytest_asyncio.fixture(autouse=True)
async def _no_network():
    """Never hit OSRM/Overpass in tests; use the deterministic fallback line."""
    from app.services.route_service import configure_osrm

    configure_osrm(client=None, fallback=True)
    yield


@pytest_asyncio.fixture
async def db(_database):
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(_database):
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def otp_code(monkeypatch):
    monkeypatch.setattr("app.services.otp_service.generate_otp", lambda *_: "123456")
    yield "123456"


async def _create_driver(session, phone: str, name: str | None = None) -> Driver:
    driver = Driver(phone=phone, name=name)
    session.add(driver)
    await session.commit()
    await session.refresh(driver)
    return driver


async def _create_verified_bus(
    session, driver: Driver, bus_number="12I", rto="TN32A0001", bus_name=None
) -> Bus:
    bus = Bus(
        driver_id=driver.id,
        bus_number=bus_number,
        rto_number=rto,
        bus_name=bus_name,
        bus_type="govt" if not bus_name else "private",
        verification_status="approved",
    )
    session.add(bus)
    await session.commit()
    await session.refresh(bus)
    return bus


async def _village_id(session, district_name: str, village_name: str) -> int:
    row = await session.execute(
        select(Village)
        .join(District, District.id == Village.district_id)
        .where(District.name == district_name, Village.name == village_name)
    )
    return row.scalar_one().id


@pytest_asyncio.fixture
async def fixtures(db):
    """Shared test-building helpers bound to the current session."""

    async def make_route(from_village: str, to_village: str):
        from app.services.route_service import build_route

        fv = await db.get(
            Village, await _village_id(db, "Villupuram", from_village)
        )
        tv = await db.get(
            Village, await _village_id(db, "Villupuram", to_village)
        )
        result = await build_route(db, fv.district_id, fv, tv)
        return result.route

    async def village_id(district_name: str, village_name: str) -> int:
        return await _village_id(db, district_name, village_name)

    return {
        "create_driver": _create_driver,
        "create_verified_bus": _create_verified_bus,
        "village_id": village_id,
        "make_route": make_route,
        "db": db,
    }
