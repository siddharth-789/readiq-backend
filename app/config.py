from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:root@localhost:5432/postgres"
    db_schema: str = "booksummary"
    redis_url: str = "redis://localhost:6379/0"
    job_queue: str = "book_generation"

    # Origins allowed to call the API from the browser (the frontend dev server).
    cors_origins: list[str] = [
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
