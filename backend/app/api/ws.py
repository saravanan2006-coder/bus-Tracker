"""Live WebSocket feed: subscribe a public client to a bus's position stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.deps import Broker, Tracking
from app.services.tracking_service import bus_channel

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/bus/{bus_id}")
async def ws_bus_stream(websocket: WebSocket, bus_id: int, tracking: Tracking, broker: Broker):
    await websocket.accept()
    try:
        # Send the last known position immediately so the map is not blank.
        live = await tracking.get_live_position(bus_id)
        if live is not None:
            await websocket.send_text(json.dumps(live))

        async for payload in broker.subscribe(bus_channel(bus_id)):
            await websocket.send_text(json.dumps(payload))
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
