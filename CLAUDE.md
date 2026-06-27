# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is the full context for this repo. Read it completely before writing
any code, suggesting changes, or answering questions. Every decision here was
made deliberately. Do not suggest alternatives unless asked.

---

## What this service is

The controller for a book summary platform. It serves a public read API over
Postgres and dispatches book generation jobs to a separate agents service via
Redis. It is intentionally thin: fast reads, lightweight writes, no heavy logic.

This is one of three repos:

- `booksummary-backend` (this repo): FastAPI, public API, job dispatch, DB schema
- `booksummary-agents`: the AI generation pipeline (summaries, embeddings)
- `booksummary-frontend`: Astro website that renders published content

All three share the same Postgres and Redis instance, which this repo brings up
via `docker-compose.yml`.

---

## Commands

```bash
# Start infrastructure (Postgres + Redis)
docker compose up -d

# Load schema (run once, or after schema changes)
psql -U postgres -d postgres -f db/schema_website_v1.sql

# Install dependencies (project uses uv, not pip)
uv sync

# Run the dev server (uvicorn reads UVICORN_* env vars natively)
uvicorn main:app --reload
# API docs:    http://127.0.0.1:8000/docs
# Health:      http://127.0.0.1:8000/health

# Override host/port if needed
UVICORN_HOST=0.0.0.0 UVICORN_PORT=8080 uvicorn main:app --reload
```

There is no test suite yet.

---

## Architecture

```
Browser
  |
  v
FastAPI (this repo, port 8000)
  |-- reads published rows --> Postgres (pgvector/pg16, db=postgres, schema=booksummary)
  |-- enqueues job ---------> Redis list "book_generation"
                                |
                                v
                         booksummary-agents
                           runs pipeline, writes results back to Postgres
```

The backend never waits for generation. The ingest endpoint creates a book row,
marks it `processing`, pushes a job onto Redis, and returns immediately with the
book id.

### Request flow

1. `POST /api/books` (api_ingest.py) calls `repository.create_book()`, returns the new row in `new` status.
2. `POST /api/books/{id}/generate` (api_ingest.py) fetches the book, validates status is `new` or `failed`, transitions to `processing`, calls `queue.enqueue_generation()`, returns 202.
3. `GET /api/books` and `GET /api/books/{slug}` (api_books.py) serve only `published` rows.

The asyncpg pool is initialised in the FastAPI lifespan (`app/main.py`). Both the pool and the Redis client are closed in the lifespan `finally` block. pgvector is registered per connection via the `init` callback; `search_path` is set to `booksummary` via `server_settings` so all queries hit the right schema without qualifying table names.

---

## Database

- **Host**: localhost:5432
- **Database name**: `postgres`
- **Schema**: `booksummary` (set automatically via `search_path` in `db.init_pool`)
- **Schema file**: `db/schema_website_v1.sql` — run this once to create tables

### books

Key fields:
- `id` uuid PK, `title`, `author`, `isbn` (unique nullable), `publication_year`
- `language` default `en`, `tags` text[] (GIN indexed)
- `copyright_status`: `public_domain` | `in_copyright` | `permission_granted`
- `source_type`: `name_only` | `pdf` | `url`
- `source_ref`: storage path or URL of input file, NULL for name_only
- `one_paragraph_summary`, `full_summary`
- `slug` unique: website URL path (nullable; auto-generation not yet implemented)
- `status`: `new` | `processing` | `ready` | `published` | `failed`
- `error_message`: set by agents service on failure
- `web_published_at`: non-null on live rows; public API filters on this

### chapters

Key fields:
- `id` uuid PK, `book_id` FK (cascade delete)
- `chapter_number` int, `chapter_title`, `summary`, `word_count`
- `embedding` vector(1536): NULL until V1.2
- `model` text: embedding model name, for re-embedding on model change
- UNIQUE constraint on (book_id, chapter_number)

### Tables coming in later phases (do not add them now)

- V1.1: `sources` (critique and support with stance, reference URL, verified flag)
- V1.2: `comments` (reader comments with moderation status)

---

## Status machine

```
new -> processing -> ready -> published
              |
              v
            failed
```

- The agents service owns `processing` to `ready`/`failed`.
- `POST /api/books/{id}/generate` accepts `new` or `failed` books (allows retry).
- Publishing is currently manual SQL:
  `UPDATE booksummary.books SET status = 'published', web_published_at = now() WHERE id = '...';`

Next task: `POST /api/books/{id}/publish` endpoint to replace that manual step.

---

## Job queue — connecting to booksummary-agents

The backend communicates with booksummary-agents exclusively through a Redis list.

- Queue name: `JOB_QUEUE` env var (default `book_generation`)
- Payload: `{"book_id": "<uuid string>"}`
- Direction: backend does `LPUSH`, agents service does `BRPOP`

The agents service must connect to the same Redis instance and listen on the same queue name. Both services share the same `.env` values for `REDIS_URL` and `JOB_QUEUE`.

---

## Configuration (app/config.py)

All settings are loaded from environment variables (`.env` file via pydantic-settings).
Copy `.env.example` to `.env` to get started.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | asyncpg DSN for Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `JOB_QUEUE` | `book_generation` | Redis list name for generation jobs |
| `CORS_ORIGINS` | localhost:4321 | Allowed browser origins |

---

## Tech decisions (do not change these without discussion)

### asyncpg, not SQLAlchemy or any other ORM

Raw SQL in a repository layer. All queries live in `repository.py`. Do not introduce an ORM.

### pydantic-settings for config

All settings in `Settings` in `config.py`, loaded from env vars. No config files, no hardcoded values. Every new setting goes in `Settings` with a sensible default where possible.

### No admin, no authentication, no login

No admin panel, no user accounts, no API keys, no auth middleware. Upload gating is a frontend concern (`PUBLIC_ENABLE_UPLOAD` in the frontend repo). The ingest endpoints are always mounted here.

### Redis for the job queue

Simple Redis list (`LPUSH` / `BRPOP`). Queue abstraction lives in `queue.py`. Do not add Kafka, Celery, or any other broker.

### uv for dependency management

Use `uv add <package>` to add dependencies — this updates both `pyproject.toml` and `uv.lock`. Do not use pip directly; there is no pip in the venv.

---

## Conventions

- No double dashes anywhere: not in Python comments, not in SQL, not in strings. Use block comments in SQL (`/* ... */`) and `#` in Python.
- No em dashes in any output or generated content.
- SQL: snake_case columns and table names. No native enum types; use text + CHECK constraint.
- UUID PKs generated with `gen_random_uuid()`. All timestamps `timestamptz`. `ON DELETE CASCADE` on all FKs.
- `updated_at` maintained by a trigger, not application code.
- Enum validation happens in `models.py` before the DB CHECK fires (see `COPYRIGHT_STATUSES`, `SOURCE_TYPES`, `BOOK_STATUSES`).

---

## What NOT to do

- Do not store full book text in the database. Only derived content (summaries).
- Do not store media files in the database or repo. Only file paths or URLs.
- Do not add a Postgres enum type. Use text + CHECK.
- Do not add an ORM.
- Do not add admin endpoints or authentication middleware.
- Do not add a backend feature flag for generation. Upload gating is frontend-only.
- Do not add the V1.1 sources table or V1.2 comments table until those phases start.
- Do not hardcode secrets anywhere in the code.
- Do not use pip; use uv.

---

## Phasing

- V1 (current): book metadata input, whole-book summary, chapter summaries, published to the website.
- V1.1 (next): sourced critique and support with reference links (new `sources` table).
- V1.2 (later): RAG chat over chapter embeddings, reader comments (new `comments` table).
- Phase 2 (future): YouTube video generation pipeline.
