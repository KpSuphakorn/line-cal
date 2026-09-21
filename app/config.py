from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from ipaddress import ip_address
from urllib.parse import urlparse


def normalize_postgres_url(url: str) -> str:
    """Use the psycopg2 SQLAlchemy dialect for both common Postgres schemes."""
    value = url.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg2://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg2://", 1)
    return value


def is_postgres_url(url: str) -> bool:
    return url.strip().lower().startswith(("postgres://", "postgresql://", "postgresql+"))


def postgres_connect_args(url: str) -> dict[str, str]:
    """Return safe driver options; never log or expose the URL itself."""
    return {"sslmode": "require"} if is_postgres_url(url) else {}


def is_secure_production_webapp_url(url: str) -> bool:
    """Accept only a public HTTPS origin for the production LIFF app."""
    try:
        parsed = urlparse(url.strip())
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not parsed.netloc or not hostname:
            return False
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            return False
        try:
            address = ip_address(hostname)
        except ValueError:
            address = None
        return not address or not (address.is_loopback or address.is_unspecified)
    except ValueError:
        return False


class Settings(BaseSettings):
    APP_ENV: str = Field(default="development")
    # LINE Messaging API
    LINE_CHANNEL_SECRET: str = Field(default="mock_line_channel_secret")
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(default="mock_line_channel_access_token")
    LINE_LOGIN_CHANNEL_ID: Optional[str] = Field(default=None)
    LIFF_ID: Optional[str] = Field(default=None)
    WEBAPP_BASE_URL: str = Field(default="http://localhost:8000/webapp")

    # Google Gemini API
    GEMINI_API_KEY: str = Field(default="mock_gemini_api_key")

    # App Settings
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    DATABASE_URL: str = Field(default="sqlite:///./line_cal.db")
    MIGRATION_DATABASE_URL: Optional[str] = Field(default=None)
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=20)
    DB_MAX_OVERFLOW: int = Field(default=2, ge=0, le=20)
    MAX_UPLOAD_BYTES: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    ALLOWED_IMAGE_TYPES: str = Field(default="image/jpeg,image/png,image/webp")
    AI_DAILY_LIMIT: int = Field(default=30, ge=1, le=10000)
    STRENGTH_MET: float = Field(default=3.5, ge=1.0, le=12.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()


def validate_production_settings() -> None:
    """Fail closed for settings that would make production insecure."""
    if settings.APP_ENV.lower() not in {"production", "prod"}:
        return
    database_url = settings.DATABASE_URL.strip().lower()
    if not is_postgres_url(database_url):
        raise RuntimeError("Invalid production settings: DATABASE_URL must use PostgreSQL")
    required = {
        "LINE_CHANNEL_SECRET": settings.LINE_CHANNEL_SECRET,
        "LINE_CHANNEL_ACCESS_TOKEN": settings.LINE_CHANNEL_ACCESS_TOKEN,
        "LINE_LOGIN_CHANNEL_ID": settings.LINE_LOGIN_CHANNEL_ID,
        "LIFF_ID": settings.LIFF_ID,
        "WEBAPP_BASE_URL": settings.WEBAPP_BASE_URL,
        "GEMINI_API_KEY": settings.GEMINI_API_KEY,
    }
    missing = [name for name, value in required.items() if not value or str(value).startswith("mock_")]
    if missing:
        raise RuntimeError(f"Missing secure production settings: {', '.join(missing)}")
    if not is_secure_production_webapp_url(settings.WEBAPP_BASE_URL):
        raise RuntimeError("Invalid production settings: WEBAPP_BASE_URL must be a public HTTPS URL")
