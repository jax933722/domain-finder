"""Application configuration.

All settings are loaded from environment variables (or a local ``.env`` file)
so the same image can be promoted from development to production without code
changes. Values that carry secrets never have hard-coded production defaults.
"""

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- General ----
    PROJECT_NAME: str = "Company Domain Enrichment"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ---- Security ----
    SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION_super_secret_key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # First admin bootstrapped on startup (optional).
    FIRST_ADMIN_EMAIL: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None

    # ---- CORS ----
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl | str] = ["http://localhost:5173", "http://localhost"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _assemble_cors(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # ---- Database ----
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "domainfinder"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ---- Redis ----
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Celery uses separate logical DBs so job state and broker do not collide.
    CELERY_BROKER_DB: int = 1
    CELERY_RESULT_DB: int = 2

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.CELERY_BROKER_DB}"

    @property
    def celery_result_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.CELERY_RESULT_DB}"

    # ---- Cache ----
    DOMAIN_CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 30  # 30 days, configurable

    # ---- Search providers ----
    # Preferred provider first. Empty keys are simply skipped at runtime.
    BRAVE_SEARCH_API_KEY: str | None = None
    GOOGLE_CSE_API_KEY: str | None = None
    GOOGLE_CSE_ENGINE_ID: str | None = None
    BING_SEARCH_API_KEY: str | None = None

    # Ordered list of providers to attempt. Overridable via env (comma list).
    SEARCH_PROVIDER_ORDER: List[str] = ["brave", "google", "bing", "wikipedia"]

    @field_validator("SEARCH_PROVIDER_ORDER", mode="before")
    @classmethod
    def _assemble_providers(cls, v):
        if isinstance(v, str):
            return [i.strip().lower() for i in v.split(",") if i.strip()]
        return v

    # ---- Domain discovery tuning ----
    SEARCH_TIMEOUT_SECONDS: float = 15.0
    SEARCH_MAX_RETRIES: int = 3
    SEARCH_BACKOFF_BASE: float = 0.5
    HTTP_MAX_CONNECTIONS: int = 100
    HTTP_MAX_KEEPALIVE: int = 20
    # Minimum confidence (0-1) required to accept a domain, else NOT FOUND.
    CONFIDENCE_THRESHOLD: float = 0.6
    # Max concurrent company lookups inside a single processing job.
    JOB_CONCURRENCY: int = 10

    # ---- Uploads ----
    MAX_UPLOAD_ROWS: int = 200_000
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024  # 100 MB
    UPLOAD_DIR: str = "/data/uploads"
    RESULT_DIR: str = "/data/results"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
