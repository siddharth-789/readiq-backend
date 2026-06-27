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


class BookStatus(str, Enum):
    new = "new"
    processing = "processing"
    ready = "ready"
    published = "published"
    failed = "failed"


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
    source_type: SourceType
    source_ref: str | None = None


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
    web_published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BookDetail(Book):
    chapters: list[Chapter] = Field(default_factory=list)
