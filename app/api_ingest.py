from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app import repository
from app.db import get_pool
from app.models import Book, BookCreate
from app.queue import enqueue_generation

router = APIRouter(prefix="/api/books", tags=["ingest"])


@router.post("", response_model=Book, status_code=201)
async def create_book(data: BookCreate):
    """Create a book row in 'new' status. Generation is a separate step."""
    pool = get_pool()
    return await repository.create_book(pool, data)


@router.post("/{book_id}/generate", response_model=Book, status_code=202)
async def generate_book(book_id: UUID):
    """Dispatch the book to the agents service for AI summarisation."""
    pool = get_pool()
    book = await repository.get_book_by_id(pool, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status not in ("new", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot dispatch generation for a book in '{book.status}' status",
        )
    updated = await repository.update_book_status(pool, book_id, "processing")
    await enqueue_generation(str(book_id))
    return updated
