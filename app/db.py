import asyncpg
from pgvector.asyncpg import register_vector

from app.config import get_settings

_pool: asyncpg.Pool | None = None


async def _on_connect(conn: asyncpg.Connection) -> None:
    """Register the pgvector type codec on each new pool connection."""
    await register_vector(conn)


async def init_pool() -> asyncpg.Pool:
    """Create the module-level asyncpg pool, pinning search_path to the app schema."""
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=10,
        init=_on_connect,
        server_settings={"search_path": settings.db_schema},
    )
    return _pool


async def close_pool() -> None:
    """Close and clear the module-level pool, if one is open."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the initialised pool, or raise if init_pool() hasn't run yet."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool
