import pytest
from pathlib import Path

from app.config import (
    is_secure_production_webapp_url,
    normalize_postgres_url,
    postgres_connect_args,
    settings,
    validate_production_settings,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("postgres://user:pass@example.test/db", "postgresql+psycopg2://user:pass@example.test/db"),
        ("postgresql://user:pass@example.test/db", "postgresql+psycopg2://user:pass@example.test/db"),
        ("postgresql+psycopg2://user:pass@example.test/db", "postgresql+psycopg2://user:pass@example.test/db"),
    ],
)
def test_normalize_postgres_url(value, expected):
    assert normalize_postgres_url(value) == expected


def test_postgres_connections_require_ssl_without_exposing_url():
    assert postgres_connect_args("postgresql+psycopg2://user:secret@example.test/db") == {"sslmode": "require"}
    assert postgres_connect_args("sqlite:///./line_cal.db") == {}


def test_production_rejects_sqlite_database_url(monkeypatch):
    """Production must not silently run on a local SQLite file."""
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "sqlite:///./line_cal.db",
        "LINE_CHANNEL_SECRET": "line-secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "line-access-token",
        "LINE_LOGIN_CHANNEL_ID": "1234567890",
        "LIFF_ID": "1234567890-abcdef",
        "WEBAPP_BASE_URL": "https://example.test/webapp",
        "GEMINI_API_KEY": "genuine-gemini-key",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)

    with pytest.raises(RuntimeError, match="DATABASE_URL.*PostgreSQL"):
        validate_production_settings()


def test_production_rejects_missing_or_mock_gemini_api_key(monkeypatch):
    """A missing/mock Gemini key must not silently ship fabricated food analyses."""
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://user:pass@example.test/db",
        "LINE_CHANNEL_SECRET": "line-secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "line-access-token",
        "LINE_LOGIN_CHANNEL_ID": "1234567890",
        "LIFF_ID": "1234567890-abcdef",
        "WEBAPP_BASE_URL": "https://example.test/webapp",
        "GEMINI_API_KEY": "mock_gemini_api_key",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        validate_production_settings()


def test_docker_command_uses_runtime_port_with_local_default():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
    assert "${PORT:-8000}" in dockerfile
    assert "--host 0.0.0.0" in dockerfile


@pytest.mark.parametrize(
    "value",
    [
        "http://example.test/webapp",
        "https://localhost/webapp",
        "https://127.0.0.1/webapp",
        "https://[::1]/webapp",
        "https://0.0.0.0/webapp",
    ],
)
def test_production_webapp_url_rejects_insecure_or_local(value):
    assert is_secure_production_webapp_url(value) is False


def test_production_webapp_url_accepts_public_https():
    assert is_secure_production_webapp_url("https://line-cal.example.com/webapp") is True


def test_production_rejects_local_webapp_url(monkeypatch):
    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://user:pass@example.test/db",
        "LINE_CHANNEL_SECRET": "line-secret",
        "LINE_CHANNEL_ACCESS_TOKEN": "line-access-token",
        "LINE_LOGIN_CHANNEL_ID": "1234567890",
        "LIFF_ID": "1234567890-abcdef",
        "WEBAPP_BASE_URL": "http://localhost:8000/webapp",
        "GEMINI_API_KEY": "genuine-gemini-key",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    with pytest.raises(RuntimeError, match="WEBAPP_BASE_URL.*HTTPS"):
        validate_production_settings()
