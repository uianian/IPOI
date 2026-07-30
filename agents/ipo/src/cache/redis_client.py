from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from src.config import settings


class RedisClient:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def init(self) -> None:
        self._client = aioredis.from_url(
            settings.database.redis_url,
            decode_responses=True,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not initialized. Call init() first.")
        return self._client

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ttl_hours: int | None = None) -> None:
        if ttl_hours is None:
            ttl_hours = settings.database.cache_ttl_hours
        await self.client.set(key, value, ex=ttl_hours * 3600)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        import json
        val = await self.get(key)
        if val is None:
            return None
        return json.loads(val)

    async def set_json(self, key: str, value: dict[str, Any], ttl_hours: int | None = None) -> None:
        import json
        await self.set(key, json.dumps(value, ensure_ascii=False), ttl_hours)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)