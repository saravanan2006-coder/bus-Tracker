"""Pub/sub broker abstraction backed by Redis, with in-memory fallback."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from app.config import settings


class PubSubBroker:
    async def publish(self, channel: str, payload: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError


class RedisBroker(PubSubBroker):
    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def publish(self, channel: str, payload: dict) -> None:
        await self._client.publish(channel, json.dumps(payload, ensure_ascii=False))

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        ps = self._client.pubsub()
        await ps.subscribe(channel)
        try:
            while True:
                message = await ps.get_message(
                    ignore_subscribe_messages=True, timeout=30.0
                )
                if message is None:
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode()
                if data:
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue
        finally:
            await ps.unsubscribe(channel)
            await ps.aclose()


class MemoryBroker(PubSubBroker):
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = {}

    async def publish(self, channel: str, payload: dict) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        for queue in list(self._queues.get(channel, ())):
            if queue.full():
                # Drop oldest so slow consumers cannot exhaust memory.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.setdefault(channel, set()).add(queue)
        try:
            while True:
                message = await queue.get()
                try:
                    yield json.loads(message)
                except json.JSONDecodeError:
                    continue
        finally:
            self._queues[channel].discard(queue)
            if not self._queues[channel]:
                self._queues.pop(channel, None)

    async def close(self) -> None:
        self._queues.clear()


_broker: PubSubBroker | None = None
_lock = asyncio.Lock()


async def get_broker() -> PubSubBroker:
    global _broker
    async with _lock:
        if _broker is None:
            if settings.redis_enabled and not settings.is_sqlite and not settings.debug:
                client = aioredis.from_url(settings.redis_url, decode_responses=False)
                await client.ping()
                _broker = RedisBroker(client)
            else:
                _broker = MemoryBroker()
        return _broker


async def reset_runtime() -> None:
    """Close and drop the cached broker. Used by tests for isolation."""
    global _broker
    async with _lock:
        if _broker is not None:
            await _broker.close()
            _broker = None
