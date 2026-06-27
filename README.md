# Book summary service

FastAPI backend for the book summary website. It serves a public read API from
Postgres and, when generation is enabled, exposes admin endpoints to ingest books
and (next step) generate their summaries.

## Stack

- FastAPI (async)
- asyncpg connection pool with a thin repository layer (raw SQL, no ORM)
- pgvector for chapter embeddings
- pydantic-settings for config

## Setup

1. Create and activate a virtual environment:

   ```
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Create the schema (from the project root that holds the DDL file):

   ```
   psql -d booksummary -f schema_website_v1.sql
   ```

4. Copy the env file and fill in your database URL:

   ```
   cp .env.example .env
   ```

## Run

```
python run.py
```

Then open `http://127.0.0.1:8000/docs` for the interactive API.

## The generation flag

`ENABLE_GENERATION` controls whether the admin ingest and generation endpoints
are mounted. Set it `true` locally so you can add books and generate content. In
production set it `false`: the admin routes are not registered at all, so the live
site can only read published rows. The same code and the same database power both.

## Structure

```
app/
  config.py       settings and the generation flag
  db.py           asyncpg pool, pgvector registration
  models.py       pydantic input and output schemas
  repository.py   data access over books and chapters
  api_books.py    public read endpoints
  api_admin.py    admin ingest + generate (flag gated)
  main.py         app wiring and lifespan
run.py            local dev server
```

## What is next

The `POST /api/admin/books/{book_id}/generate` endpoint is a stub. The next step
is the generation pipeline behind it: PDF ingest, chapter detection, hierarchical
summarization, and writing the rows this API already serves.
