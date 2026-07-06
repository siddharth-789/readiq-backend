from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app import repository
from app.db import get_pool
from app.models import CommentCreate, CommentOut

router = APIRouter(prefix="/api/books", tags=["comments"])

_MIN_BODY = 10
_MAX_BODY = 1000
_MAX_NAME = 80


@router.get(
    "/{book_id}/comments",
    response_model=list[CommentOut],
)
async def list_comments(book_id: UUID):
    pool = get_pool()
    rows = await repository.get_approved_comments(pool, book_id)
    return [CommentOut(**dict(r)) for r in rows]


@router.post(
    "/{book_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(book_id: UUID, data: CommentCreate):
    # Honeypot check: bots fill hidden fields, humans leave them empty
    if data.honeypot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid submission",
        )

    # Validation
    name = data.author_name.strip()
    email = data.author_email.strip().lower()
    body = data.body.strip()

    if not name or len(name) > _MAX_NAME:
        raise HTTPException(
            status_code=422,
            detail=f"Name must be between 1 and {_MAX_NAME} characters",
        )

    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(
            status_code=422,
            detail="A valid email address is required",
        )

    if len(body) < _MIN_BODY:
        raise HTTPException(
            status_code=422,
            detail=f"Comment must be at least {_MIN_BODY} characters",
        )

    if len(body) > _MAX_BODY:
        raise HTTPException(
            status_code=422,
            detail=f"Comment must be under {_MAX_BODY} characters",
        )

    pool = get_pool()

    # Verify book exists and is published
    book = await pool.fetchrow(
        "SELECT id FROM books WHERE id = $1 AND status = 'published'",
        book_id,
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    row = await repository.create_comment(
        pool, book_id, name, email, body
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already left a comment on this book. "
                   "It will appear once approved.",
        )

    return CommentOut(**dict(row))
