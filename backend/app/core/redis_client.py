"""Redis client wrapper with an in-memory fallback for dev/tests.

The application only ever depends on this thin interface, so it can run
with a real Redis in production and without one in tests.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis

from app.config import settings


class KeyValueStore:
    """Minimal async key-value interface implemented by both backends."""

    async def get(self, key: str) -> str | None:  # pragma: no cover
        raise NotImplementedError

    async def set(self, key: str, value: str, ex: int | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    async def incr(self, key: str) -> int:  # pragma: no cover
        raise NotImplementedError

    async def expire(self, key: str, seconds: int) -> None:  # pragma: no cover
        raise NotImplementedError

    async def ttl(self, key: str) -> int:  # pragma: no cover
        raise NotImplementedError

    async def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError


class RedisStore(KeyValueStore):
    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await self._client.set(key, value, ex=ex)

    async def incr(self, key: str) -> int:
        return int(await self._client.incr(key))

    async def expire(self, key: str, seconds: int) -> None:
        await self._client.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        return int(await self._client.ttl(key))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def close(self) -> None:
        await self._client.aclose()


class MemoryStore(KeyValueStore):
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def _expired(self, key: str) -> bool:
        entry = self._data.get(key)
        if entry is None:
            return True
        value, exp_at = entry
        return exp_at is not None and time.monotonic() > exp_at

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            self._data.pop(key, None)
            return None
        return self._data[key][0]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        exp_at = time.monotonic() + ex if ex is not None else None
        self._data[key] = (value, exp_at)

    async def incr(self, key: str) -> int:
        current = await self.get(key)
        new = int(current) + 1 if current else 1
        await self.set(key, str(new), ex=10)
        return new

    async def expire(self, key: str, seconds: int) -> None:
        entry = self._data.get(key)
        if entry is not None:
            self._data[key] = (entry[0], time.monotonic() + seconds)

    async def ttl(self, key: str) -> int:
        entry = self._data.get(key)
        if entry is None:
            return -2
        if entry[1] is None:
            return -1
        return max(0, int(entry[1] - time.monotonic()))

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def close(self) -> None:
        self._data.clear()


_store: KeyValueStore | None = None
_lock = asyncio.Lock()


async def get_store() -> KeyValueStore:
    """Return the process-wide store, connecting to Redis lazily."""
    global _store
    async with _lock:
        if _store is None:
            if settings.redis_enabled and not settings.is_sqlite and not settings.debug:
                client = aioredis.from_url(settings.redis_url, decode_responses=False)
                await client.ping()
                _store = RedisStore(client)
            else:
                _store = MemoryStore()
        return _store


async def reset_runtime() -> None:
    """Close and drop the cached store. Used by tests for isolation."""
    global _store
    async with _lock:
        if _store is not None:
            await _store.close()
            _store = None
