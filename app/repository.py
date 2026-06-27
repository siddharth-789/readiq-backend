from uuid import UUID

import asyncpg

from app.models import Book, BookCreate, BookDetail, Chapter

_BOOK_COLUMNS = """
    id, title, author, isbn, publication_year, language, tags,
    copyright_status, source_type, source_ref,
    one_paragraph_summary, full_summary, slug, status,
    web_published_at, created_at, updated_at
"""

_CHAPTER_COLUMNS = """
    id, book_id, chapter_number, chapter_title, summary, word_count, created_at
"""


async def list_published_books(
    pool: asyncpg.Pool, limit: int = 50, offset: int = 0
) -> list[Book]:
    rows = await pool.fetch(
        f"""
        SELECT {_BOOK_COLUMNS} FROM books
        WHERE status = 'published'
        ORDER BY web_published_at DESC NULLS LAST
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [Book(**dict(r)) for r in rows]


async def get_chapters(pool: asyncpg.Pool, book_id: UUID) -> list[Chapter]:
    rows = await pool.fetch(
        f"""
        SELECT {_CHAPTER_COLUMNS} FROM chapters
        WHERE book_id = $1
        ORDER BY chapter_number
        """,
        book_id,
    )
    return [Chapter(**dict(r)) for r in rows]


async def get_book_by_slug(
    pool: asyncpg.Pool, slug: str, published_only: bool = True
) -> BookDetail | None:
    query = f"SELECT {_BOOK_COLUMNS} FROM books WHERE slug = $1"
    if published_only:
        query += " AND status = 'published'"
    row = await pool.fetchrow(query, slug)
    if row is None:
        return None
    chapters = await get_chapters(pool, row["id"])
    return BookDetail(**dict(row), chapters=chapters)


async def get_book_by_id(pool: asyncpg.Pool, book_id: UUID) -> Book | None:
    row = await pool.fetchrow(
        f"SELECT {_BOOK_COLUMNS} FROM books WHERE id = $1",
        book_id,
    )
    return Book(**dict(row)) if row else None


async def update_book_status(
    pool: asyncpg.Pool, book_id: UUID, status: str
) -> Book | None:
    row = await pool.fetchrow(
        f"""
        UPDATE books SET status = $1
        WHERE id = $2
        RETURNING {_BOOK_COLUMNS}
        """,
        status,
        book_id,
    )
    return Book(**dict(row)) if row else None


async def create_book(pool: asyncpg.Pool, data: BookCreate) -> Book:
    row = await pool.fetchrow(
        f"""
        INSERT INTO books (
            title, author, isbn, publication_year, language, tags,
            copyright_status, source_type, source_ref
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING {_BOOK_COLUMNS}
        """,
        data.title,
        data.author,
        data.isbn,
        data.publication_year,
        data.language,
        data.tags,
        data.copyright_status,
        data.source_type,
        data.source_ref,
    )
    return Book(**dict(row))
