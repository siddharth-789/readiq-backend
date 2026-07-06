import re
from uuid import UUID

import asyncpg

from app.models import Book, BookCreate, BookDetail, Chapter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_BOOK_COLUMNS = """
    id, title, author, isbn, publication_year, language, tags,
    copyright_status, source_type, source_ref,
    one_paragraph_summary, full_summary, slug, status,
    web_published_at, created_at, updated_at, research_status
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


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-")


async def _generate_unique_slug(pool: asyncpg.Pool, author: str | None, title: str) -> str:
    title_part = _slugify(title)
    base = f"{_slugify(author)}/{title_part}" if author else title_part

    slug = base
    suffix = 1
    while await pool.fetchval("SELECT 1 FROM books WHERE slug = $1", slug):
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


async def create_book(
    pool: asyncpg.Pool,
    data: BookCreate,
    source_type: str,
    source_ref: str | None,
) -> Book:
    slug = await _generate_unique_slug(pool, data.author, data.title)
    row = await pool.fetchrow(
        f"""
        INSERT INTO books (
            title, author, isbn, publication_year, language, tags,
            copyright_status, source_type, source_ref, slug
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING {_BOOK_COLUMNS}
        """,
        data.title,
        data.author,
        data.isbn,
        data.publication_year,
        data.language,
        data.tags,
        data.copyright_status,
        source_type,
        source_ref,
        slug,
    )
    return Book(**dict(row))


# Users
async def create_user(
    pool: asyncpg.Pool, email: str, password_hash: str
) -> UUID:
    row = await pool.fetchrow(
        "INSERT INTO users (email, password_hash) "
        "VALUES ($1, $2) RETURNING id",
        email, password_hash,
    )
    return row["id"]


async def get_user_by_email(pool: asyncpg.Pool, email: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT id, email, password_hash FROM users WHERE email = $1",
        email,
    )


# Sessions
async def get_or_create_session(
    pool: asyncpg.Pool, book_id: UUID, user_id: UUID
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions (book_id, user_id)
        VALUES ($1, $2)
        ON CONFLICT (book_id, user_id) DO UPDATE
        SET book_id = EXCLUDED.book_id
        RETURNING id
        """,
        book_id, user_id,
    )
    return row["id"]


# Messages
async def get_session_messages(
    pool: asyncpg.Pool, session_id: UUID, limit: int = 8
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, session_id, role, content, created_at
        FROM chat_messages
        WHERE session_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        session_id, limit,
    )


async def save_message(
    pool: asyncpg.Pool, session_id: UUID, role: str, content: str
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        INSERT INTO chat_messages (session_id, role, content)
        VALUES ($1, $2, $3)
        RETURNING id, session_id, role, content, created_at
        """,
        session_id, role, content,
    )


# Rate limiting
async def count_user_messages_today(
    pool: asyncpg.Pool, user_id: UUID, book_id: UUID
) -> int:
    row = await pool.fetchrow(
        """
        SELECT COALESCE(messages_today, 0) AS messages_today
        FROM chat_daily_usage
        WHERE user_id = $1 AND book_id = $2
        """,
        user_id, book_id,
    )
    return row["messages_today"] if row else 0


# Book context for chat
async def get_book_chat_context(
    pool: asyncpg.Pool, book_id: UUID
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id, title, author
        FROM books
        WHERE id = $1 AND status = 'published'
        """,
        book_id,
    )


# Comments
async def get_approved_comments(
    pool: asyncpg.Pool,
    book_id: UUID,
) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, book_id, author_name, body, created_at
        FROM comments
        WHERE book_id = $1 AND status = 'approved'
        ORDER BY created_at DESC
        """,
        book_id,
    )


async def create_comment(
    pool: asyncpg.Pool,
    book_id: UUID,
    author_name: str,
    author_email: str,
    body: str,
) -> asyncpg.Record | None:
    """
    Insert a comment in pending status.
    Returns None if the email already has a pending or approved
    comment on this book (duplicate constraint).
    """
    try:
        return await pool.fetchrow(
            """
            INSERT INTO comments
                (book_id, author_name, author_email, body, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING id, book_id, author_name, body, created_at
            """,
            book_id,
            author_name.strip(),
            author_email.strip().lower(),
            body.strip(),
        )
    except Exception as exc:
        # Unique constraint violation means duplicate submission
        if "idx_comments_book_email" in str(exc):
            return None
        raise
