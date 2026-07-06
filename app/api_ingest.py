from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app import repository
from app.config import get_settings
from app.db import get_pool
from app.models import Book, BookCreate, CopyrightStatus
from app.queue import enqueue_generation
from app.upload import save_upload

router = APIRouter(prefix="/api/books", tags=["ingest"])


@router.post("", response_model=Book, status_code=201)
async def create_book(
    title: str = Form(...),
    author: str | None = Form(None),
    isbn: str | None = Form(None),
    publication_year: str | None = Form(None),
    language: str = Form("en"),
    tags: str | None = Form(None),
    copyright_status: CopyrightStatus = Form(...),
    file: UploadFile | None = File(None),
):
    """Create a book row in 'new' status, optionally attaching a PDF."""
    parsed_year = int(publication_year) if publication_year else None
    parsed_tags = (
        [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    )

    data = BookCreate(
        title=title,
        author=author,
        isbn=isbn,
        publication_year=parsed_year,
        language=language,
        tags=parsed_tags,
        copyright_status=copyright_status,
    )

    source_type = "name_only"
    source_ref = None

    ALLOWED_TYPES = {
        "application/pdf": ".pdf",
        "application/epub+zip": ".epub",
    }

    if file is not None:
        file_ext = Path(file.filename).suffix.lower()
        expected_ext = ALLOWED_TYPES.get(file.content_type)

        if expected_ext is None or file_ext != expected_ext:
            raise HTTPException(
                status_code=422,
                detail=f"File must be a PDF or EPUB. "
                    f"Got content type '{file.content_type}' "
                    f"with extension '{file_ext}'.",
            )

        settings = get_settings()
        file_bytes = await file.read()
        if len(file_bytes) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum upload size of {settings.max_upload_bytes} bytes",
            )

        source_ref = save_upload(file_bytes, file.filename, settings.upload_dir)
        source_type = file_ext.lstrip(".")  # produces 'pdf' or 'epub'

    pool = get_pool()
    return await repository.create_book(pool, data, source_type, source_ref)


@router.post("/{book_id}/generate", response_model=Book, status_code=202)
async def generate_book(book_id: UUID):
    """Dispatch the book to the agents service for AI summarisation."""
    pool = get_pool()
    book = await repository.get_book_by_id(pool, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status not in ("new", "failed") and book.research_status not in ('pending', 'failed', 'skipped'):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot dispatch generation for a book in '{book.status}' status",
        )
    updated = await repository.update_book_status(pool, book_id, "processing")
    await enqueue_generation(str(book_id))
    return updated
