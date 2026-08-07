"""End-to-end tracking flow tests via the public API."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Bus, LocationPoint, Trip
from app.services.tracking_service import bus_channel


async def _driver_token(db, phone="+919812345678"):
    from tests.conftest import _create_driver

    driver = await _create_driver(db, phone)
    return driver, create_access_token(driver.id)


async def _setup_bus_and_route(db, fixtures, token, client, bus_number="12I"):
    """Register a bus, build a route, assign it, and return the bus."""
    resp = await client.post(
        "/api/v1/driver/buses",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_number": bus_number, "rto_number": "TN32A7777", "bus_type": "govt"},
    )
    assert resp.status_code == 200, resp.text
    bus_id = resp.json()["id"]

    from_village = await fixtures["village_id"]("Villupuram", "Villupuram")
    to_village = await fixtures["village_id"]("Villupuram", "Tindivanam")

    resp = await client.post(
        "/api/v1/driver/routes/build",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "district_id": 1,
            "from_village_id": from_village,
            "to_village_id": to_village,
        },
    )
    assert resp.status_code == 200, resp.text
    route_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/driver/buses/{bus_id}/assign-route",
        headers={"Authorization": f"Bearer {token}"},
        json={"route_id": route_id},
    )
    assert resp.status_code == 200
    return bus_id, route_id


async def test_full_tracking_flow(db, client, fixtures):
    driver, token = await _driver_token(db)
    bus_id, route_id = await _setup_bus_and_route(db, fixtures, token, client)

    # Start a trip.
    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    assert resp.status_code == 200, resp.text
    trip_id = resp.json()["id"]
    assert resp.json()["status"] == "active"

    # Share a location.
    resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 11.94, "lng": 79.50, "speed_kmh": 35.0},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["data"]["accepted"] is True

    # Live position must now be visible to the public.
    resp = await client.get(f"/api/v1/buses/{bus_id}")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["live"] is not None
    assert body["live"]["lat"] == 11.94
    assert body["route"] is not None
    assert body["eta"] is not None
    assert "eta_minutes" in body["eta"]
    assert body["eta"]["next_stop"] is not None
    assert body["eta"]["next_stop"]["village"] is not None
    assert body["eta"]["next_stop"]["village"]["name"]

    # End the trip.
    resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Location persisted to the database.
    count = await db.scalar(
        select(LocationPoint).where(LocationPoint.trip_id == trip_id)
    )
    assert count is not None
    assert count.trip_id == trip_id


async def test_teleport_flagged_anomalous(db, client, fixtures):
    driver, token = await _driver_token(db, phone="+919812345679")
    bus_id, route_id = await _setup_bus_and_route(db, fixtures, token, client, "5J")

    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    trip_id = resp.json()["id"]

    # First fix near the route start.
    await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 11.94, "lng": 79.50, "speed_kmh": 30.0},
    )
    # Respect the 1/sec rate limit, then teleport ~40km in ~1s.
    await asyncio.sleep(1.1)
    resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 12.30, "lng": 79.60, "speed_kmh": 40.0},
    )
    assert resp.status_code == 202
    assert resp.json()["data"]["anomalous"] is True

    # The anomalous fix is stored but flagged.
    point = await db.scalar(
        select(LocationPoint)
        .where(LocationPoint.trip_id == trip_id)
        .order_by(LocationPoint.id.desc())
    )
    assert point.is_anomalous is True


async def test_location_rate_limit(db, client, fixtures):
    driver, token = await _driver_token(db, phone="+919812345680")
    bus_id, route_id = await _setup_bus_and_route(db, fixtures, token, client, "8K")
    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    trip_id = resp.json()["id"]
    for _ in range(2):
        resp = await client.post(
            f"/api/v1/driver/trips/{trip_id}/location",
            headers={"Authorization": f"Bearer {token}"},
            json={"lat": 11.94, "lng": 79.50},
        )
    assert resp.status_code == 429


async def test_memory_broker_pubsub():
    from app.core.pubsub import MemoryBroker

    broker = MemoryBroker()
    received = []

    async def consumer():
        async for payload in broker.subscribe(bus_channel(1)):
            received.append(payload)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await broker.publish(bus_channel(1), {"bus_id": 1, "lat": 11.94, "lng": 79.5})
    await asyncio.sleep(0.05)
    task.cancel()
    assert received and received[0]["lat"] == 11.94
