from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import api_auth, api_books, api_chat, api_comments, api_ingest
from app.config import get_settings
from app.db import close_pool, init_pool
from app.queue import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init the DB pool on startup; close pool and Redis client on shutdown."""
    await init_pool()
    try:
        yield
    finally:
        await close_pool()
        await close_redis()


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS middleware, all routers (api_books last), and /health."""
    settings = get_settings()
    app = FastAPI(title="Book Summary API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # api_books is registered last: its GET /{slug:path} catch-all would
    # otherwise shadow any other GET route nested under /api/books/{id}/...
    app.include_router(api_ingest.router)
    app.include_router(api_auth.router)
    app.include_router(api_chat.router)
    app.include_router(api_comments.router)
    app.include_router(api_books.router)

    @app.get("/health")
    async def health():
        """Liveness check."""
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":

    import os
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
    )

