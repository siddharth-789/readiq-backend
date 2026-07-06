from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:root@localhost:5432/postgres"
    db_schema: str = "readiq"
    redis_url: str = "redis://localhost:6379/0"
    job_queue: str = "book_generation"
    upload_dir: str = "D:\\readiq\\books\\source_ref"
    max_upload_bytes: int = 52_428_800  # 50 MB

    agents_chat_url: str = "http://127.0.0.1:8001/chat"
    jwt_secret: str = "local-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days
    daily_chat_limit: int = 5
    max_history_messages: int = 8

    # Origins allowed to call the API from the browser (the frontend dev server).
    cors_origins: list[str] = [
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
