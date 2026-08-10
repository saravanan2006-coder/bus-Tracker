"""Alert worker tests: proximity -> push, de-duplication, re-arm."""
from __future__ import annotations

from sqlalchemy import update

from app.config import settings
from app.core.pubsub import get_broker
from app.core.redis_client import get_store
from app.models import AlertSubscription, Bus, Village
from app.services.alert_worker import alert_worker_tick
from app.services.tracking_service import TrackingService

from tests.conftest import _create_driver
from tests.test_tracking import _driver_token, _setup_bus_and_route


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs) -> bool:
        self.sent.append(kwargs)
        return True


async def _tracking():
    return TrackingService(await get_store(), await get_broker())


async def _start_live_bus(db, client, fixtures):
    """Register + route + start a trip for a bus and return (bus_id, trip_id)."""
    driver, token = await _driver_token(db, phone="+919812345690")
    bus_id, route_id = await _setup_bus_and_route(
        db, fixtures, token, client, "31M"
    )
    resp = await client.post(
        "/api/v1/driver/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"bus_id": bus_id, "route_id": route_id},
    )
    return bus_id, resp.json()["id"], token


async def _post_location(client, token, trip_id, lat, lng):
    return await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        headers={"Authorization": f"Bearer {token}"},
        json={"lat": lat, "lng": lng, "speed_kmh": 40.0},
    )


async def _subscribe(client, bus_id, stop_village_id, distance_m, token="dev-1"):
    return await client.post(
        "/api/v1/alerts",
        json={
            "device_id": token,
            "bus_id": bus_id,
            "stop_village_id": stop_village_id,
            "fcm_token": f"fcm-{token}",
            "distance_m": distance_m,
        },
    )


async def test_alert_fires_once_and_does_not_duplicate(db, client, fixtures):
    bus_id, trip_id, token = await _start_live_bus(db, client, fixtures)
    tindivanam = await fixtures["village_id"]("Villupuram", "Tindivanam")
    # Bus near Tindivanam (the route destination, ~500 m away).
    await _post_location(client, token, trip_id, 12.2300, 79.6554)
    resp = await _subscribe(client, bus_id, tindivanam, distance_m=1000)
    assert resp.status_code == 200, resp.text

    sender = _FakeSender()
    tracking = await _tracking()
    result = await alert_worker_tick(db, sender, tracking)
    assert result["fired"] == 1
    assert result["skipped"] == 0
    assert len(sender.sent) == 1
    assert sender.sent[0]["token"] == "fcm-dev-1"
    assert sender.sent[0]["data"]["bus_id"] == str(bus_id)

    # A second scan must not re-fire while the bus is still within range.
    again = await alert_worker_tick(db, sender, tracking)
    assert again["fired"] == 0
    assert len(sender.sent) == 1

    sub = await db.get(AlertSubscription, resp.json()["data"]["subscription_id"])
    assert sub is not None and sub.triggered is True


async def test_alert_rearms_then_fires_again(db, client, fixtures, monkeypatch):
    # The location endpoint is rate-limited to 1/sec per driver; this test
    # moves the bus several times quickly, so lift the limit.
    monkeypatch.setattr(settings, "max_location_rate_per_second", 100)
    bus_id, trip_id, token = await _start_live_bus(db, client, fixtures)
    tindivanam = await fixtures["village_id"]("Villupuram", "Tindivanam")
    await _post_location(client, token, trip_id, 12.2300, 79.6554)
    await _subscribe(client, bus_id, tindivanam, distance_m=1000)

    sender = _FakeSender()
    tracking = await _tracking()
    first = await alert_worker_tick(db, sender, tracking)
    assert first["fired"] == 1

    # Bus pulls away (to the route start, ~33 km from Tindivanam) -> re-arm.
    await _post_location(client, token, trip_id, 11.9400, 79.4947)
    second = await alert_worker_tick(db, sender, tracking)
    assert second["rearmed"] == 1

    # Next approach fires again.
    await _post_location(client, token, trip_id, 12.2300, 79.6554)
    third = await alert_worker_tick(db, sender, tracking)
    assert third["fired"] == 1
    assert len(sender.sent) == 2


async def test_alert_skips_without_live_bus_or_token(db, client, fixtures):
    bus_id, trip_id, token = await _start_live_bus(db, client, fixtures)
    tindivanam = await fixtures["village_id"]("Villupuram", "Tindivanam")

    # Subscription for a second bus that has never shared a location.
    driver = await _create_driver(db, "+919812345691")
    other = Bus(
        driver_id=driver.id,
        bus_number="32N",
        rto_number="TN32A0002",
        verification_status="approved",
    )
    db.add(other)
    await db.commit()
    await db.refresh(other)

    resp = await _subscribe(client, other.id, tindivanam, distance_m=1000)
    assert resp.status_code == 200

    sender = _FakeSender()
    tracking = await _tracking()
    result = await alert_worker_tick(db, sender, tracking)
    assert result["scanned"] == 1
    assert result["fired"] == 0
    assert sender.sent == []

    # A subscription without an FCM token is not even scanned.
    await _subscribe(client, bus_id, tindivanam, distance_m=1000, token="no-token")
    await db.execute(
        update(AlertSubscription)
        .where(AlertSubscription.fcm_token == "fcm-no-token")
        .values(fcm_token=None)
    )
    await db.commit()
    result = await alert_worker_tick(db, sender, tracking)
    assert result["scanned"] == 1  # only the live-bus subscription remains


async def test_alert_skips_stop_unknown_on_route(db, client, fixtures):
    bus_id, trip_id, token = await _start_live_bus(db, client, fixtures)
    # A stop village with coordinates but not on this bus's route is fine,
    # but a village with no coordinates anywhere must be skipped.
    village = Village(
        district_id=1,
        taluk_id=1,
        name="Undisclosed Test Village",
        name_normalized="undisclosed-test-village",
        place_type="village",
        has_coords=False,
        needs_review=True,
    )
    db.add(village)
    await db.commit()
    await db.refresh(village)

    await _post_location(client, token, trip_id, 12.2300, 79.6554)
    resp = await _subscribe(client, bus_id, village.id, distance_m=5000)
    assert resp.status_code == 200

    sender = _FakeSender()
    tracking = await _tracking()
    result = await alert_worker_tick(db, sender, tracking)
    assert result["fired"] == 0
    assert result["skipped"] == 1
    assert sender.sent == []
