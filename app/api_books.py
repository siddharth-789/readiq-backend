from uuid import UUID

from fastapi import APIRouter, HTTPException

from app import repository
from app.db import get_pool
from app.models import Book, BookDetail

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=list[Book])
async def list_books(limit: int = 50, offset: int = 0):
    """List published books, most recently published first."""
    pool = get_pool()
    return await repository.list_published_books(pool, limit=limit, offset=offset)


@router.get("/{book_id}/sources")
async def get_sources(book_id: UUID):
    """List a book's critique/support sources, ordered by stance then creation time."""
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT id, stance, source_type, title,
               author_or_outlet, reference_url, insight, created_at
        FROM sources
        WHERE book_id = $1
        ORDER BY stance, created_at
        """,
        book_id,
    )
    return [dict(r) for r in rows]


@router.get("/{slug:path}", response_model=BookDetail)
async def get_book(slug: str):
    """Fetch a published book with its chapters by slug.

    Path-converter catch-all (slugs may contain '/'); must stay the last
    router registered so it doesn't shadow other GET routes under /api/books/{id}/...
    """
    pool = get_pool()
    book = await repository.get_book_by_slug(pool, slug, published_only=True)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
