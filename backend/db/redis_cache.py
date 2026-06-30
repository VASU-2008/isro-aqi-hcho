import redis.asyncio as aioredis
import os
import json
from typing import Any

_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    return _client


async def get_cached(key: str) -> Any | None:
    try:
        val = await get_client().get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def set_cached(key: str, value: Any, ttl: int = 86400):
    try:
        await get_client().setex(key, ttl, json.dumps(value))
    except Exception:
        pass


async def close():
    global _client
    if _client:
        await _client.aclose()
        _client = None
