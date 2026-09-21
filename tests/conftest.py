"""Force the ordinary test command onto disposable local settings.

This module is imported by pytest before test collection, so the application's
Settings and global SQLAlchemy engine can never consume a developer's real
.env credentials or Supabase URL during local tests.
"""
import atexit
import json
import os
import tempfile

import pytest


_database_file = tempfile.NamedTemporaryFile(prefix="line-cal-pytest-", suffix=".db", delete=False)
_database_file.close()

os.environ.update({
    "APP_ENV": "testing",
    "DATABASE_URL": f"sqlite:///{_database_file.name}",
    "MIGRATION_DATABASE_URL": f"sqlite:///{_database_file.name}",
    "LINE_CHANNEL_SECRET": "mock_line_channel_secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "mock_line_channel_access_token",
    "LINE_LOGIN_CHANNEL_ID": "mock_line_login_channel_id",
    "LIFF_ID": "mock_liff_id",
    "WEBAPP_BASE_URL": "http://testserver/webapp",
    "GEMINI_API_KEY": "mock_gemini_api_key",
})


@atexit.register
def _remove_test_database() -> None:
    try:
        os.unlink(_database_file.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def boom_genai():
    """A fake google.generativeai module whose model always fails to call."""
    class _BoomModel:
        def generate_content(self, *args, **kwargs):
            raise RuntimeError("upstream unavailable")

    class _BoomGenAI:
        @staticmethod
        def configure(**kwargs):
            pass

        @staticmethod
        def GenerativeModel(*args, **kwargs):
            return _BoomModel()

    return _BoomGenAI()


@pytest.fixture
def flaky_genai_factory():
    """A fake google.generativeai module that fails on one model name and succeeds on any other.

    The returned module records every generate_content kwargs set on
    `.calls`, so tests can assert how the request was configured.
    """
    def _make(failing_model: str, success_items: list[dict]):
        calls: list[dict] = []

        class _Response:
            text = json.dumps({"items": success_items})

        class _Model:
            def __init__(self, name):
                self.name = name

            def generate_content(self, *args, **kwargs):
                calls.append({"model": self.name, **kwargs})
                if self.name == failing_model:
                    raise RuntimeError("429 quota exceeded")
                return _Response()

        class _FlakyGenAI:
            calls: list[dict] = []

            @staticmethod
            def configure(**kwargs):
                pass

            @staticmethod
            def GenerativeModel(name, *args, **kwargs):
                return _Model(name)

        _FlakyGenAI.calls = calls
        return _FlakyGenAI()

    return _make
