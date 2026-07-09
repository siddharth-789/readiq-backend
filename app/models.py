from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class CopyrightStatus(str, Enum):
    """Legal basis for hosting a book's content."""

    public_domain = "public_domain"
    in_copyright = "in_copyright"
    permission_granted = "permission_granted"


class SourceType(str, Enum):
    """How a book's source material was supplied at ingest."""

    name_only = "name_only"
    pdf = "pdf"
    url = "url"
    epub = "epub"


class BookStatus(str, Enum):
    """Generation pipeline state: new -> processing -> ready -> published, or failed."""

    new = "new"
    processing = "processing"
    ready = "ready"
    published = "published"
    failed = "failed"

class ResearchStatus(str, Enum):
    """State of the separate sourced-critique/support research step."""

    pending = "pending"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class ChapterBase(BaseModel):
    """Fields shared by chapter creation and read models."""

    chapter_number: int
    chapter_title: str | None = None
    summary: str | None = None
    word_count: int | None = None


class Chapter(ChapterBase):
    """A persisted chapter row."""

    id: UUID
    book_id: UUID
    created_at: datetime


class BookCreate(BaseModel):
    """Payload for creating a new book (parsed from the multipart ingest form)."""

    title: str
    author: str | None = None
    isbn: str | None = None
    publication_year: int | None = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    copyright_status: CopyrightStatus


class Book(BaseModel):
    """A persisted book row, as returned by the public and ingest APIs."""

    id: UUID
    title: str
    author: str | None
    isbn: str | None
    publication_year: int | None
    language: str
    tags: list[str]
    copyright_status: CopyrightStatus
    source_type: SourceType
    source_ref: str | None
    one_paragraph_summary: str | None
    full_summary: str | None
    slug: str | None
    status: BookStatus
    research_status: ResearchStatus
    web_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BookDetail(Book):
    """A single book with its chapters, returned by the book detail endpoint."""

    chapters: list[Chapter] = Field(default_factory=list)


# Auth
class UserRegister(BaseModel):
    """Registration payload: email + plaintext password to be hashed."""

    email: str
    password: str


class UserLogin(BaseModel):
    """Login payload: email + plaintext password to verify."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """JWT issued on successful register/login."""

    access_token: str
    token_type: str = "bearer"


# Chat
class ChatMessageOut(BaseModel):
    """A single stored chat message (user or assistant turn)."""

    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class ChatAsk(BaseModel):
    """Payload for asking a question in a book's chat."""

    question: str


class ChatAnswerResponse(BaseModel):
    """Chat answer plus the caller's remaining daily quota."""

    answer: str
    session_id: UUID
    messages_used_today: int
    messages_remaining: int


# Comments
class CommentCreate(BaseModel):
    """Payload for submitting a comment; honeypot must stay empty (bot filter)."""

    author_name: str
    author_email: str
    body: str
    honeypot: str = ""  # must be empty string, bots fill this


class CommentOut(BaseModel):
    """Public comment representation; author_email is deliberately omitted."""

    id: UUID
    book_id: UUID
    author_name: str
    body: str
    created_at: datetime
    # Note: author_email is intentionally excluded from public output
