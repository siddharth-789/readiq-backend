import json

import redis.asyncio as redis

from app.config import get_settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def enqueue_generation(book_id: str) -> None:
    settings = get_settings()
    client = _get_client()
    await client.lpush(settings.job_queue, json.dumps({"book_id": book_id}))


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
