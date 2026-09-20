"""Force the ordinary test command onto disposable local settings.

This module is imported by pytest before test collection, so the application's
Settings and global SQLAlchemy engine can never consume a developer's real
.env credentials or Supabase URL during local tests.
"""
import atexit
import os
import tempfile


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
