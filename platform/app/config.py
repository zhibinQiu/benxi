from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "doc-platform"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = (
        "postgresql+psycopg2://platform:platform@127.0.0.1:5432/platform"
    )

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8
    refresh_token_expire_days: int = 7

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False
    minio_region: str = "us-east-1"

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@local"

    cors_origins: str = "*"

    pdf2zh_api_url: str = "http://127.0.0.1:7861"

    @property
    def broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
