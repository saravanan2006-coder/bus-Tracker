"""Sliding-window rate limiter backed by the key-value store."""
from __future__ import annotations

from app.core.redis_client import KeyValueStore


class RateLimiter:
    def __init__(self, store: KeyValueStore, limit: int, window_seconds: int) -> None:
        self._store = store
        self._limit = limit
        self._window = window_seconds

    async def allow(self, key: str) -> bool:
        """Return True if the key is within its limit for the window."""
        counter_key = f"rl:{self._window}:{key}"
        count = await self._store.incr(counter_key)
        if count == 1:
            await self._store.expire(counter_key, self._window)
        return count <= self._limit

    async def remaining(self, key: str) -> int:
        counter_key = f"rl:{self._window}:{key}"
        ttl = await self._store.ttl(counter_key)
        if ttl < 0:
            return self._limit
        count = await self._store.get(counter_key)
        used = int(count or 0)
        return max(0, self._limit - used)
