# Book summary service

FastAPI backend for the book summary platform. It serves a public read API
over Postgres, accepts book ingestion (with optional PDF/EPUB upload),
dispatches generation jobs to a separate agents service over Redis, and hosts
chat and comments for published books.

## Stack

- FastAPI (async)
- asyncpg connection pool with a thin repository layer (raw SQL, no ORM)
- pgvector for chapter embeddings
- pydantic-settings for config
- bcrypt + python-jose for chat auth (JWT)
- httpx for the synchronous chat call to the agents service

## Setup

1. Install dependencies (the project uses `uv`, not `pip`):

   ```
   uv sync
   ```

2. Start Postgres and Redis:

   ```
   docker compose up -d
   ```

3. Load the schema:

   ```
   psql -U postgres -d postgres -f db/schema_website_v1.sql
   ```

4. Copy the env file and adjust as needed:

   ```
   cp .env.example .env
   ```

## Run

```
uvicorn main:app --reload
```

Then open `http://127.0.0.1:8000/docs` for the interactive API.

## Endpoints

There is no admin flag and no auth on ingestion or public reads. Auth exists
only for chat (`POST /api/auth/register`, `POST /api/auth/login`, and the
`/api/books/{id}/chat*` routes), because chat usage is rate-limited per user
per book.

- `POST /api/books` — create a book (multipart form, optional PDF/EPUB file)
- `POST /api/books/{id}/generate` — dispatch generation to the agents service via Redis
- `GET /api/books`, `GET /api/books/{slug}` — public reads of published books
- `GET /api/books/{book_id}/sources` — sourced critique/support links
- `POST /api/books/{id}/chat`, `GET /api/books/{id}/chat/history` — auth required
- `GET|POST /api/books/{book_id}/comments` — public, unauthenticated, comments require manual SQL approval

## Structure

```
main.py             app wiring, lifespan, entrypoint (repo root, not app/)
app/
  config.py         pydantic-settings config
  db.py             asyncpg pool, pgvector registration
  queue.py          Redis job queue (generation dispatch)
  models.py         pydantic input and output schemas
  repository.py     all SQL, no ORM
  upload.py         PDF/EPUB upload sanitizing and storage
  auth.py           bcrypt hashing, JWT issuance/verification
  deps.py           get_current_user_id FastAPI dependency
  api_ingest.py     book creation and generation dispatch
  api_books.py      public read endpoints (books, sources)
  api_auth.py       register/login
  api_chat.py       chat (auth required)
  api_comments.py   comments (public, moderation via SQL)
db/schema_website_v1.sql   full schema (books, chapters, sources, users, chat, comments)
```

See `CLAUDE.md` for the full architectural context, phasing, and conventions.
