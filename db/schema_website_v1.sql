/* V1 schema: books and chapters */

/* pgvector must live in public so register_vector() can find it (it hardcodes schema='public') */
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

CREATE SCHEMA IF NOT EXISTS booksummary;

SET search_path = booksummary;

/* Trigger function to keep updated_at current */
CREATE OR REPLACE FUNCTION booksummary.set_updated_at()
RETURNS TRIGGER AS $func$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$func$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS booksummary.books (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    title                 text        NOT NULL,
    author                text,
    isbn                  text        UNIQUE,
    publication_year      int,
    language              text        NOT NULL DEFAULT 'en',
    tags                  text[]      NOT NULL DEFAULT '{}',
    copyright_status      text        NOT NULL
        CHECK (copyright_status IN ('public_domain', 'in_copyright', 'permission_granted')),
    source_type           text        NOT NULL
        CHECK (source_type IN ('name_only', 'pdf', 'url')),
    source_ref            text,
    one_paragraph_summary text,
    full_summary          text,
    slug                  text        UNIQUE,
    status                text        NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'processing', 'ready', 'published', 'failed')),
    error_message         text,
    web_published_at      timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE TRIGGER books_updated_at
    BEFORE UPDATE ON booksummary.books
    FOR EACH ROW EXECUTE FUNCTION booksummary.set_updated_at();

CREATE INDEX IF NOT EXISTS books_tags_gin
    ON booksummary.books USING GIN (tags);

CREATE INDEX IF NOT EXISTS books_status_idx
    ON booksummary.books (status);

CREATE INDEX IF NOT EXISTS books_published_idx
    ON booksummary.books (web_published_at DESC NULLS LAST)
    WHERE web_published_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS booksummary.chapters (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id        uuid        NOT NULL
        REFERENCES booksummary.books (id) ON DELETE CASCADE,
    chapter_number int         NOT NULL,
    chapter_title  text,
    summary        text,
    word_count     int,
    embedding      vector(1536),
    model          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (book_id, chapter_number)
);

CREATE INDEX IF NOT EXISTS chapters_book_id_idx
    ON booksummary.chapters (book_id);
