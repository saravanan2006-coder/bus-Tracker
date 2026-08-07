"""Shared FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pubsub import PubSubBroker, get_broker
from app.core.redis_client import KeyValueStore, get_store
from app.core.security import decode_token
from app.database import get_db
from app.models import Driver
from app.services.tracking_service import TrackingService

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def store_dep() -> AsyncGenerator[KeyValueStore, None]:
    store = await get_store()
    yield store


Store = Annotated[KeyValueStore, Depends(store_dep)]


async def broker_dep() -> AsyncGenerator[PubSubBroker, None]:
    broker = await get_broker()
    yield broker


Broker = Annotated[PubSubBroker, Depends(broker_dep)]


async def tracking_service_dep(
    store: Store, broker: Broker
) -> AsyncGenerator[TrackingService, None]:
    yield TrackingService(store, broker)


Tracking = Annotated[TrackingService, Depends(tracking_service_dep)]


async def get_current_driver(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Driver:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Missing bearer token"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        driver_id = decode_token(token, "access")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": str(exc)},
        ) from exc
    driver = await db.get(Driver, driver_id)
    if driver is None or not driver.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Driver not found"},
        )
    return driver


CurrentDriver = Annotated[Driver, Depends(get_current_driver)]
