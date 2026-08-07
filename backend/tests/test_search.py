"""Public search tests: village pickers, route pair matching, bus lookup."""
from __future__ import annotations

from tests.test_tracking import _driver_token, _setup_bus_and_route


async def test_districts_and_villages(client):
    resp = await client.get("/api/v1/districts")
    assert resp.status_code == 200
    names = {d["name"] for d in resp.json()}
    assert "Villupuram" in names
    assert "Madurai" in names

    district = next(d for d in resp.json() if d["name"] == "Villupuram")
    assert district["taluk_count"] >= 7
    assert district["village_count"] >= 10

    resp = await client.get(f"/api/v1/districts/{district['id']}/villages")
    assert resp.status_code == 200
    villages = resp.json()
    names = {v["name"] for v in villages}
    # The forbidden example villages must never exist in the system.
    assert "Saravanampakkam" not in names
    assert "Arasur" not in names


async def test_village_search_query(client):
    resp = await client.get("/api/v1/districts/1/villages?q=tind")
    assert resp.status_code == 200
    names = {v["name"].lower() for v in resp.json()}
    assert "tindivanam" in names


async def test_route_pair_search(db, client, fixtures):
    driver, token = await _driver_token(db, phone="+919812345681")
    bus_id, route_id = await _setup_bus_and_route(db, fixtures, token, client, "21A")

    # Bus must not appear until it is on an active trip.
    from_village = await fixtures["village_id"]("Villupuram", "Villupuram")
    to_village = await fixtures["village_id"]("Villupuram", "Tindivanam")
    resp = await client.get(
        "/api/v1/routes/find",
        params={
            "district_id": 1,
            "from_village_id": from_village,
            "to_village_id": to_village,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]  # route exists
    assert all(r["buses"] == [] for r in resp.json()["data"])

    # Start a trip and share a location, then the bus appears live.
    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    trip_id = resp.json()["id"]
    await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 11.94, "lng": 79.50, "speed_kmh": 35.0},
    )
    resp = await client.get(
        "/api/v1/routes/find",
        params={
            "district_id": 1,
            "from_village_id": from_village,
            "to_village_id": to_village,
        },
    )
    assert resp.status_code == 200
    any_live = any(b["live"] for r in resp.json()["data"] for b in r["buses"])
    assert any_live is True


async def test_bus_search_by_number(client, fixtures, db):
    driver, token = await _driver_token(db, phone="+919812345682")
    await _setup_bus_and_route(db, fixtures, token, client, "99A")
    resp = await client.get("/api/v1/buses/search", params={"q": "99a"})
    assert resp.status_code == 200
    assert any(b["bus_number"] == "99A" for b in resp.json()["data"])


async def test_bus_history(client, fixtures, db):
    driver, token = await _driver_token(db, phone="+919812345683")
    bus_id, route_id = await _setup_bus_and_route(db, fixtures, token, client, "14D")
    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    trip_id = resp.json()["id"]
    await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": 11.94, "lng": 79.50, "speed_kmh": 32.0},
    )
    resp = await client.get(f"/api/v1/buses/{bus_id}/history")
    assert resp.status_code == 200
    assert len(resp.json()["data"]["trail"]) == 1


async def test_favorites_and_alerts(client):
    resp = await client.post(
        "/api/v1/favorites",
        json={"device_id": "device-1", "from_village_id": 1, "to_village_id": 2},
    )
    assert resp.status_code == 200
    resp = await client.get("/api/v1/favorites", params={"device_id": "device-1"})
    assert resp.status_code == 200
    assert resp.json()["data"]

    resp = await client.post(
        "/api/v1/alerts",
        json={
            "device_id": "device-1",
            "bus_id": 1,
            "stop_village_id": 1,
            "fcm_token": "tok",
            "distance_m": 800,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["subscription_id"]
