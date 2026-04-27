"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "HOBB API"
    APP_ENV: str = "production"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_PREFIX: str = "/api"

    # --- Database ---
    POSTGRES_USER: str = "hobb"
    POSTGRES_PASSWORD: str = "hobb_pass"
    POSTGRES_DB: str = "hobb"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Security / JWT ---
    JWT_SECRET: str = "CHANGE_ME_IN_PRODUCTION_TO_A_LONG_RANDOM_STRING"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8        # 8 hours
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14 # 14 days

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost,http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # --- File storage ---
    UPLOAD_DIR: str = "/storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp"
    IMAGE_MAX_DIMENSION: int = 2000
    IMAGE_JPEG_QUALITY: int = 85

    @property
    def allowed_image_types_list(self) -> List[str]:
        return [t.strip() for t in self.ALLOWED_IMAGE_TYPES.split(",") if t.strip()]

    # --- SMTP / Email ---
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@hobb.local"
    SMTP_USE_TLS: bool = True

    # --- Scheduler ---
    SCHEDULER_ENABLED: bool = True
    MISSED_TASK_CHECK_INTERVAL_MINUTES: int = 5
    RECURRING_TASK_GENERATION_HOUR: int = 0   # midnight server time
    REMINDER_LEAD_MINUTES: int = 30

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_DEFAULT: str = "120/minute"

    # --- Seed data ---
    SEED_ON_STARTUP: bool = True
    SEED_ADMIN_EMAIL: str = "admin@hobb.com"
    SEED_ADMIN_PASSWORD: str = "admin123"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
