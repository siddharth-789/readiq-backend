import json

import redis.asyncio as redis

from app.config import get_settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    """Lazily create and cache the module-level Redis client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def enqueue_generation(book_id: str) -> None:
    """Push a generation job for book_id onto the Redis job queue (LPUSH)."""
    settings = get_settings()
    client = _get_client()
    await client.lpush(settings.job_queue, json.dumps({"book_id": book_id}))


async def close_redis() -> None:
    """Close and clear the module-level Redis client, if one is open."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
