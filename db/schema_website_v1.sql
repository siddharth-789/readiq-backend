/* V1 schema: books and chapters */

/* pgvector must live in public so register_vector() can find it (it hardcodes schema='public') */
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

CREATE SCHEMA IF NOT EXISTS readiq;

SET search_path TO readiq, public;


/* Trigger function to keep updated_at current */
CREATE OR REPLACE FUNCTION readiq.set_updated_at()
RETURNS TRIGGER AS $func$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$func$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS readiq.books (
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
        CHECK (source_type IN ('name_only', 'pdf', 'url', 'epub')),
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
    BEFORE UPDATE ON readiq.books
    FOR EACH ROW EXECUTE FUNCTION readiq.set_updated_at();

CREATE INDEX IF NOT EXISTS books_tags_gin
    ON readiq.books USING GIN (tags);

CREATE INDEX IF NOT EXISTS books_status_idx
    ON readiq.books (status);

CREATE INDEX IF NOT EXISTS books_published_idx
    ON readiq.books (web_published_at DESC NULLS LAST)
    WHERE web_published_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS readiq.chapters (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id        uuid        NOT NULL
        REFERENCES readiq.books (id) ON DELETE CASCADE,
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
    ON readiq.chapters (book_id);

CREATE TABLE sources (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id             uuid        NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    stance              text        NOT NULL
                        CHECK (stance IN ('critique', 'support')),
    source_type         text        NOT NULL
                        CHECK (source_type IN ('book', 'article', 'academic_paper')),
    title               text        NOT NULL,
    author_or_outlet    text,
    reference_url       text        NOT NULL,
    insight             text        NOT NULL,
    about_living_person boolean     NOT NULL DEFAULT false,
    verified            boolean     NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_sources_book_id ON sources (book_id);
CREATE INDEX idx_sources_stance  ON sources (stance);

ALTER TABLE books
ADD COLUMN research_status text NOT NULL DEFAULT 'pending'
CHECK (research_status IN ('pending', 'completed', 'failed', 'skipped'));

/* Users table for chat authentication */
CREATE TABLE users (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text        NOT NULL UNIQUE,
    password_hash text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users (email);

/* Thin session table */
CREATE TABLE chat_sessions (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id    uuid        NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (book_id, user_id)
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions (user_id);
CREATE INDEX idx_chat_sessions_book_id ON chat_sessions (book_id);

/* Messages with rate limiting support */
CREATE TABLE chat_messages (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       text        NOT NULL CHECK (role IN ('user', 'assistant')),
    content    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_session_id ON chat_messages (session_id);
CREATE INDEX idx_chat_messages_created_at ON chat_messages (created_at);

/* Rate limiting view: messages sent per user per book today */
CREATE VIEW chat_daily_usage AS
SELECT
    cs.user_id,
    cs.book_id,
    COUNT(*) FILTER (WHERE cm.role = 'user') AS messages_today
FROM chat_sessions cs
JOIN chat_messages cm ON cm.session_id = cs.id
WHERE cm.created_at >= CURRENT_DATE
GROUP BY cs.user_id, cs.book_id;

/* Update chapters embedding dimension if needed */
/* Only run this if your column is not already 1536 */
/* ALTER TABLE chapters DROP COLUMN embedding; */
/* ALTER TABLE chapters ADD COLUMN embedding vector(1536); */
/* ALTER TABLE chapters ADD COLUMN model text; */

CREATE TABLE comments (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id      uuid        NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    author_name  text        NOT NULL,
    author_email text        NOT NULL,
    body         text        NOT NULL,
    status       text        NOT NULL DEFAULT 'approved'
                 CHECK (status IN ('pending', 'approved', 'hidden')),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_comments_book_id ON comments (book_id);
CREATE INDEX idx_comments_status  ON comments (status);
CREATE INDEX idx_comments_email   ON comments (author_email);

/* Prevent duplicate submissions from same email on same book */
CREATE UNIQUE INDEX idx_comments_book_email
    ON comments (book_id, author_email)
    WHERE status IN ('pending', 'approved');