"""Load test for the BusTracker public API and live feed.

Run against a deployed instance (or a local uvicorn):

    pip install locust
    locust --host https://bustracker.onrender.com --users 200 --spawn-rate 20 \
        --run-time 3m --only-summary

Scenarios:
- PublicUser  : anonymous read load (districts, taluks, villages, bus
                search/detail, history, favorites add/list).
- LiveFeedUser: maintains an open WebSocket to a bus's position stream.

The seed data must be present for realistic village ids; lookups fall back to
whatever the deployed instance returns, so this runs on any deployment.
"""
from __future__ import annotations

import json
import random

from locust import HttpUser, between, task

try:
    from locust.contrib.fasthttp import WebSocketUser

    _WS_AVAILABLE = True
except Exception:  # noqa: BLE001 - older locust versions lack WebSocketUser.
    _WS_AVAILABLE = False


class PublicUser(HttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self) -> None:
        resp = self.client.get("/api/v1/districts", name="districts")
        self.districts = resp.json() if resp.status_code == 200 else []
        if self.districts:
            self.district_id = self.districts[0]["id"]
        self.villages: list[dict] = []

    @task(3)
    def list_taluks(self) -> None:
        if not self.districts:
            return
        d = random.choice(self.districts)
        self.client.get(f"/api/v1/districts/{d['id']}/taluks", name="districts/{id}/taluks")

    @task(3)
    def list_villages(self) -> None:
        if not self.districts:
            return
        d = random.choice(self.districts)
        resp = self.client.get(
            f"/api/v1/districts/{d['id']}/villages?limit=100",
            name="districts/{id}/villages",
        )
        if resp.status_code == 200:
            self.villages = resp.json() or []

    @task(2)
    def bus_search(self) -> None:
        self.client.get("/api/v1/buses/search?q=a", name="buses/search")

    @task(2)
    def bus_detail(self) -> None:
        # Any bus id is a miss when empty; a 404 costs nothing but still
        # exercises the lookup path.
        bus_id = random.randint(1, 500)
        self.client.get(f"/api/v1/buses/{bus_id}", name="buses/{id}")

    @task(2)
    def bus_history(self) -> None:
        bus_id = random.randint(1, 500)
        self.client.get(
            f"/api/v1/buses/{bus_id}/history?minutes=30&limit=200",
            name="buses/{id}/history",
        )

    @task(1)
    def add_and_list_favorites(self) -> None:
        if len(self.villages) < 2:
            return
        a, b = random.sample(self.villages, 2)
        self.client.post(
            "/api/v1/favorites",
            json={
                "device_id": f"load-{self.id}-{random.randint(0, 9999)}",
                "from_village_id": a["id"],
                "to_village_id": b["id"],
            },
            name="favorites POST",
        )
        self.client.get(
            f"/api/v1/favorites?device_id=load-{self.id}",
            name="favorites GET",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="health")


if _WS_AVAILABLE:

    class LiveFeedUser(WebSocketUser):
        """Keeps N open /ws/bus/{id} streams (the main live scale cost)."""

        wait_time = between(60.0, 120.0)

        def on_start(self) -> None:
            # Pick a small bus id space; unconnected ids still exercise the
            # accept + last-known-position path.
            bus_id = random.randint(1, 20)
            self.client.connect(f"/api/v1/ws/bus/{bus_id}")

        @task
        def read(self) -> None:
            try:
                self.client.recv()
            except Exception:  # noqa: BLE001 - connection drop is expected
                pass
