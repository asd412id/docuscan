from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List, Optional
import os
import secrets


class Settings(BaseSettings):
    # Application
    app_name: str = "DocuScan"
    app_version: str = "1.0.0"
    debug: bool = True
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # Security
    secret_key: str = "your-super-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Trusted proxies for rate limiting (comma-separated CIDR notation)
    # Example: "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    # If not set, defaults to common private networks
    trusted_proxies: Optional[str] = None

    # Database - default to SQLite for easy development
    database_url: str = "sqlite+aiosqlite:///./docuscan.db"

    # Redis (required for Celery)
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_enabled: bool = False

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"  # Default rate limit
    rate_limit_auth: str = "10/minute"  # Login/register endpoints
    rate_limit_upload: str = "20/minute"  # File upload endpoints
    rate_limit_process: str = "30/minute"  # Processing endpoints
    rate_limit_download: str = "60/minute"  # File download endpoints

    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 20
    file_retention_minutes: int = 60

    # Tesseract
    tesseract_cmd: str = "tesseract"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url.lower()

    def generate_secret_key(self) -> str:
        """Generate a secure random secret key."""
        return secrets.token_urlsafe(32)

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
