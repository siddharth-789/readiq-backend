import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration loaded from environment variables / .env."""

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

    cors_origins_raw: str = Field(
        default="http://localhost:4321,http://127.0.0.1:4321",
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ORIGINS as a JSON list if bracketed, else a comma-separated string."""
        value = self.cors_origins_raw.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                value = value[1:-1]
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
