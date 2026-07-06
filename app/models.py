from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class CopyrightStatus(str, Enum):
    public_domain = "public_domain"
    in_copyright = "in_copyright"
    permission_granted = "permission_granted"


class SourceType(str, Enum):
    name_only = "name_only"
    pdf = "pdf"
    url = "url"
    epub = "epub"


class BookStatus(str, Enum):
    new = "new"
    processing = "processing"
    ready = "ready"
    published = "published"
    failed = "failed"

class ResearchStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class ChapterBase(BaseModel):
    chapter_number: int
    chapter_title: str | None = None
    summary: str | None = None
    word_count: int | None = None


class Chapter(ChapterBase):
    id: UUID
    book_id: UUID
    created_at: datetime


class BookCreate(BaseModel):
    title: str
    author: str | None = None
    isbn: str | None = None
    publication_year: int | None = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    copyright_status: CopyrightStatus


class Book(BaseModel):
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
    chapters: list[Chapter] = Field(default_factory=list)


# Auth
class UserRegister(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Chat
class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class ChatAsk(BaseModel):
    question: str


class ChatAnswerResponse(BaseModel):
    answer: str
    session_id: UUID
    messages_used_today: int
    messages_remaining: int


# Comments
class CommentCreate(BaseModel):
    author_name: str
    author_email: str
    body: str
    honeypot: str = ""  # must be empty string, bots fill this


class CommentOut(BaseModel):
    id: UUID
    book_id: UUID
    author_name: str
    body: str
    created_at: datetime
    # Note: author_email is intentionally excluded from public output
