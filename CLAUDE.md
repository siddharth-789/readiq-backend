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

- `readiq-backend` (this repo): FastAPI, public API, job dispatch, DB schema
- `readiq-agents`: the AI generation pipeline (summaries, embeddings)
- `readiq-frontend`: Astro website that renders published content

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
  |-- reads published rows --> Postgres (pgvector/pg16, db=postgres, schema=readiq)
  |-- enqueues job ---------> Redis list "book_generation"
                                |
                                v
                         readiq-agents
                           runs pipeline, writes results back to Postgres
```

The backend never waits for generation. The ingest endpoint creates a book row,
marks it `processing`, pushes a job onto Redis, and returns immediately with the
book id.

### Request flow

1. `POST /api/books` (api_ingest.py) accepts multipart form data (title, author,
   isbn, publication_year, language, tags, copyright_status, plus an optional
   `file`), auto-generates a unique `author-slug/title-slug` slug, and calls
   `repository.create_book()`, returning the new row in `new` status. See
   "Book creation and file upload" below.
2. `POST /api/books/{id}/generate` (api_ingest.py) fetches the book, checks its
   status is dispatchable, transitions to `processing`, calls
   `queue.enqueue_generation()`, returns 202.
3. `GET /api/books`, `GET /api/books/{book_id}/sources`, and `GET /api/books/{slug}`
   (api_books.py) serve only `published` rows. Route order matters here: see
   "Router registration order" below.
4. `POST /api/auth/register` and `POST /api/auth/login` (api_auth.py) issue a JWT for chat.
5. `POST /api/books/{id}/chat` (api_chat.py, auth required) rate-limits via `chat_daily_usage`, then calls the agents service synchronously over HTTP and stores both sides of the exchange in `chat_messages`.
6. `POST /api/books/{id}/comments` (api_comments.py, no auth) validates and inserts a `pending` comment on a published book; `GET /api/books/{id}/comments` returns only `approved` ones.

The asyncpg pool is initialised in the FastAPI lifespan (`main.py`, at the repo
root, not under `app/`). Both the pool and the Redis client are closed in the
lifespan `finally` block. pgvector is registered per connection via the `init`
callback; `search_path` is set to `readiq` via `server_settings` so all
queries hit the right schema without qualifying table names.

### Book creation and file upload

`POST /api/books` is multipart, not JSON, because it accepts metadata and an
optional source file (PDF or EPUB) in a single request:

- Required form fields: `title`, `copyright_status`.
- Optional form fields: `author`, `isbn`, `publication_year`, `language`
  (default `en`), `tags` (comma-separated, split into a list).
- Optional `file`: content type must be `application/pdf` (extension `.pdf`)
  or `application/epub+zip` (extension `.epub`); mismatches return 422. Files
  over `MAX_UPLOAD_BYTES` return 413.
- If a file is present, `app/upload.py`'s `save_upload()` sanitizes the
  filename, writes it under `UPLOAD_DIR` with a random prefix, and the book
  row's `source_type` becomes `pdf` or `epub` with `source_ref` set to the
  saved path. Without a file, `source_type` is `name_only`.
- `repository.create_book()` also generates the book's `slug` at insert time:
  `_generate_unique_slug()` slugifies `author` and `title` into
  `author-slug/title-slug` (or just `title-slug` if there is no author), and
  appends `-2`, `-3`, etc. on collision. Slug generation is no longer a
  future task; it happens on every insert.

### Router registration order

`api_books.py`'s `GET /{slug:path}` is a path-converter catch-all so slugs
containing `/` (see above) resolve correctly. Because it matches almost any
GET path under `/api/books/...`, it must be registered after every other
router that defines a GET route nested under `/api/books/{id}/...`
(`sources`, `chat/history`, `comments`). `main.py` includes `api_books.router`
last for this reason; keep it last when adding new routers.

---

## Database

- **Host**: localhost:5432
- **Database name**: `postgres`
- **Schema**: `readiq` (set automatically via `search_path` in `db.init_pool`)
- **Schema file**: `db/schema_website_v1.sql` — run this once to create tables

### books

Key fields:
- `id` uuid PK, `title`, `author`, `isbn` (unique nullable), `publication_year`
- `language` default `en`, `tags` text[] (GIN indexed)
- `copyright_status`: `public_domain` | `in_copyright` | `permission_granted`
- `source_type`: `name_only` | `pdf` | `url` | `epub`
- `source_ref`: storage path or URL of input file, NULL for name_only
- `one_paragraph_summary`, `full_summary`
- `slug` unique: `author-slug/title-slug` website URL path, auto-generated by
  `repository.create_book()` on insert (see "Book creation and file upload")
- `status`: `new` | `processing` | `ready` | `published` | `failed`
- `research_status`: `pending` | `completed` | `failed` | `skipped`, default
  `pending`. Tracks the separate sourced-critique/support research step (see
  `sources` below) independently of the main generation `status`.
- `error_message`: set by agents service on failure
- `web_published_at`: non-null on live rows; public API filters on this

### chapters

Key fields:
- `id` uuid PK, `book_id` FK (cascade delete)
- `chapter_number` int, `chapter_title`, `summary`, `word_count`
- `embedding` vector(1536): NULL until V1.2
- `model` text: embedding model name, for re-embedding on model change
- UNIQUE constraint on (book_id, chapter_number)

### sources (V1.1, live)

Key fields:
- `id` uuid PK, `book_id` FK (cascade delete)
- `stance`: `critique` | `support`
- `source_type`: `book` | `article` | `academic_paper`
- `title`, `author_or_outlet`, `reference_url`, `insight`
- `about_living_person` boolean, `verified` boolean

Served publicly (no auth, no published-only filter) via
`GET /api/books/{book_id}/sources` in api_books.py, ordered by `stance` then
`created_at`.

### Chat (pulled forward from V1.2)

Chat over book summaries (not full RAG over chapter embeddings yet) has been
pulled forward ahead of schedule. See "Chat and auth" below.

- `users`: `id` uuid PK, `email` unique, `password_hash`
- `chat_sessions`: `id` uuid PK, `book_id` FK, `user_id` FK, UNIQUE `(book_id, user_id)` (one session per user per book)
- `chat_messages`: `id` uuid PK, `session_id` FK (cascade delete), `role` (`user` | `assistant`), `content`
- `chat_daily_usage`: view aggregating `chat_messages.role = 'user'` counts per `(user_id, book_id)` for `created_at >= CURRENT_DATE`, used for rate limiting

### comments (pulled forward from V1.2, live)

Key fields:
- `id` uuid PK, `book_id` FK (cascade delete)
- `author_name`, `author_email` (never returned by the public API), `body`
- `status`: `pending` | `approved` | `hidden`, set to `pending` explicitly by
  `repository.create_comment()` on insert (the column's own DEFAULT is
  `approved`, which application code must always override)
- Unique partial index on `(book_id, author_email)` where status is `pending`
  or `approved`, so one email can only have one live comment per book
- Moderation is manual SQL only; there is no moderation UI or endpoint

---

## Status machine

```
new -> processing -> ready -> published
              |
              v
            failed
```

- The agents service owns `processing` to `ready`/`failed`.
- `POST /api/books/{id}/generate` is meant to accept `new` or `failed` books
  (allows retry). The current guard is
  `if book.status not in ("new", "failed") and book.research_status not in ("pending", "failed", "skipped")`
  (note the `and`): a book only gets rejected if *both* `status` and
  `research_status` look wrong. A book with a bad `status` but an
  otherwise-fine `research_status` (or vice versa) is not blocked. This may
  be an `and`/`or` bug rather than intended behavior; worth a second look.
- Publishing is currently manual SQL:
  `UPDATE readiq.books SET status = 'published', web_published_at = now() WHERE id = '...';`

Next task: `POST /api/books/{id}/publish` endpoint to replace that manual step.

---

## Job queue — connecting to readiq-agents

Book generation dispatch (name/pdf ingestion to summaries) goes exclusively
through a Redis list. This is unchanged.

- Queue name: `JOB_QUEUE` env var (default `book_generation`)
- Payload: `{"book_id": "<uuid string>"}`
- Direction: backend does `LPUSH`, agents service does `BRPOP`

The agents service must connect to the same Redis instance and listen on the same queue name. Both services share the same `.env` values for `REDIS_URL` and `JOB_QUEUE`.

## Chat — synchronous HTTP call to readiq-agents

Chat answers are needed inline for a request/response UI, so `POST /api/books/{id}/chat`
calls the agents service directly over internal HTTP (`AGENTS_CHAT_URL`), unlike
generation dispatch. This is the one exception to "Redis only" and exists because
chat cannot be fire-and-forget: the caller is waiting on an answer.

- The backend sends `book_id`, `question`, and recent `history` as JSON. It does
  not forward book metadata (title, author, summaries); the agents service is
  expected to look that up itself from `book_id` if it needs it.
- The agents service responds with `{"answer": str}`.
- `AGENTS_CHAT_URL` is an internal-only URL. Never expose it to the browser.
- If the agents service is unreachable or errors, the backend returns 502.

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
| `UPLOAD_DIR` | `D:\readiq\books\source_ref` | Directory uploaded PDF/EPUB source files are saved to |
| `MAX_UPLOAD_BYTES` | `52428800` (50 MB) | Max accepted upload size |
| `AGENTS_CHAT_URL` | `http://127.0.0.1:8001/chat` | Internal HTTP endpoint on the agents service for chat answers |
| `JWT_SECRET` | dev placeholder, must be overridden in prod | Signing secret for chat auth tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `10080` (7 days) | Chat auth token lifetime |
| `DAILY_CHAT_LIMIT` | `5` | Max chat messages per user per book per day |
| `MAX_HISTORY_MESSAGES` | `8` | Number of recent chat messages sent to the agents service as context |

---

## Tech decisions (do not change these without discussion)

### asyncpg, not SQLAlchemy or any other ORM

Raw SQL in a repository layer. All queries live in `repository.py`. Do not introduce an ORM.

### pydantic-settings for config

All settings in `Settings` in `config.py`, loaded from env vars. No config files, no hardcoded values. Every new setting goes in `Settings` with a sensible default where possible.

### No admin. Auth exists only for chat.

There is still no admin panel and no API keys. Upload gating remains a frontend
concern (`PUBLIC_ENABLE_UPLOAD` in the frontend repo), and the ingest and public
read endpoints remain unauthenticated.

The one exception: chat requires a logged-in user, because chat usage is
rate-limited per user per book. `app/auth.py` (bcrypt password hashing, JWT
issuance/verification) and `app/deps.py` (`get_current_user_id` FastAPI
dependency) exist to support `POST /api/auth/register`, `POST /api/auth/login`,
and the `/api/books/{id}/chat*` routes only. Do not add auth to any other
endpoint, and do not build password reset, email verification, OAuth, or
social login.

### Redis for the job queue

Simple Redis list (`LPUSH` / `BRPOP`). Queue abstraction lives in `queue.py`. Do not add Kafka, Celery, or any other broker.

### uv for dependency management

Use `uv add <package>` to add dependencies — this updates both `pyproject.toml` and `uv.lock`. Do not use pip directly; there is no pip in the venv. `requirements.txt` is not the source of truth; keep it in sync with `pyproject.toml` if it is touched, but prefer editing `pyproject.toml`/`uv.lock` via `uv add`.

Current dependencies beyond the FastAPI/asyncpg/pgvector/pydantic-settings/redis
core: `bcrypt` (password hashing), `python-jose[cryptography]` (JWT), `httpx`
(sync-style HTTP client for the chat call to the agents service).

### docker-compose

`docker-compose.yml`'s `backend` service (profile `app`) only sets
`DATABASE_URL`, `DB_SCHEMA`, `REDIS_URL`, and `JOB_QUEUE`. It does not set
`UPLOAD_DIR`, `MAX_UPLOAD_BYTES`, `AGENTS_CHAT_URL`, `JWT_SECRET`,
`JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `DAILY_CHAT_LIMIT`, or
`MAX_HISTORY_MESSAGES`, so running the backend via
`docker compose --profile app up` silently falls back to `config.py`'s
defaults for all of those, including the placeholder `JWT_SECRET`. Update the
compose file's environment block when running the backend containerized with
chat/upload/comments in play.

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
- Do not add admin endpoints. Do not add auth to any endpoint besides chat.
- Do not add a backend feature flag for generation. Upload gating is frontend-only.
- Do not build a moderation UI or moderation endpoints. Approval is manual SQL only.
- Do not build email notifications for comments.
- Do not build comment editing or deletion by users.
- Do not add auth to the comments endpoints.
- Do not build password reset, email verification, OAuth, or social login for chat auth.
- Do not lower the bcrypt work factor from its default.
- Do not call the agents service over HTTP for anything except chat. Generation dispatch stays on Redis.
- Do not hardcode secrets anywhere in the code.
- Do not use pip; use uv.

---

## Phasing

- V1 (done): book metadata input, whole-book summary, chapter summaries, published to the website.
- V1.1 (done): sourced critique and support with reference links (`sources` table).
- Chat (current, pulled forward from V1.2): authenticated Q&A per book, backed by
  `users`/`chat_sessions`/`chat_messages`, rate-limited via the `chat_daily_usage`
  view, answered synchronously by the agents service over internal HTTP. This is
  chat over the whole-book/one-paragraph summary, not full RAG over chapter
  embeddings.
- Comments (current, pulled forward from V1.2): unauthenticated, honeypot-checked
  submission on published books; requires manual SQL approval before appearing
  in the public `GET .../comments` list. `author_email` is never exposed publicly
  and is used only to enforce one live comment per email per book.
- V1.2 (remaining): RAG chat over chapter embeddings.
- Phase 2 (future): YouTube video generation pipeline.
