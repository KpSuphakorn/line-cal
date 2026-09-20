import asyncio
from time import time

import httpx
import pytest
from fastapi import HTTPException

from app import auth
from app.config import settings


VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


def _claims(audience: str = "channel-123"):
    return {
        "iss": "https://access.line.me",
        "aud": audience,
        "sub": "Uverified-line-subject",
        "exp": int(time()) + 3600,
        "name": "Test User",
    }


def test_verify_line_id_token_sends_configured_client_id(monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "channel-123")
    calls = []
    response = httpx.Response(200, json=_claims(), request=httpx.Request("POST", VERIFY_URL))

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 5.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return response

    monkeypatch.setattr(auth.httpx, "AsyncClient", FakeClient)
    user = asyncio.run(auth.verify_line_id_token("signed-token"))

    assert user.subject == "Uverified-line-subject"
    assert calls == [(VERIFY_URL, {"data": {"id_token": "signed-token", "client_id": "channel-123"}})]


def test_verify_line_id_token_rejects_mismatched_audience(monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "channel-123")
    response = httpx.Response(200, json=_claims(audience="another-channel"), request=httpx.Request("POST", VERIFY_URL))

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(auth.httpx, "AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.verify_line_id_token("signed-token"))

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid LINE token audience"


def test_verify_line_id_token_rejects_invalid_http_response(monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "channel-123")
    response = httpx.Response(
        401,
        json={"error": "invalid_request"},
        request=httpx.Request("POST", VERIFY_URL),
    )

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(auth.httpx, "AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.verify_line_id_token("invalid-token"))

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid LINE ID token"


def test_verify_line_id_token_fails_closed_without_channel_configuration(monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", None)

    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.verify_line_id_token("signed-token"))

    assert error.value.status_code == 503
