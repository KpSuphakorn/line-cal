"""Authentication for LIFF API requests.

LINE's ID token is verified server-side. The browser never chooses an owner.
"""
from dataclasses import dataclass
from time import time
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException

from app.config import settings


@dataclass(frozen=True)
class AuthenticatedUser:
    subject: str
    name: str | None = None


async def verify_line_id_token(token: str) -> AuthenticatedUser:
    if not token:
        raise HTTPException(status_code=401, detail="Missing LINE ID token")
    channel_id = (settings.LINE_LOGIN_CHANNEL_ID or "").strip()
    if not channel_id:
        # Production configuration validation requires this value.  Fail
        # closed in development too instead of asking LINE to verify a token
        # without binding it to this application's channel.
        raise HTTPException(status_code=503, detail="LINE Login channel is not configured")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                "https://api.line.me/oauth2/v2.1/verify",
                data={"id_token": token, "client_id": channel_id},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("LINE token claims must be an object")
        claims: dict[str, Any] = payload
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid LINE ID token") from exc

    if claims.get("iss") != "https://access.line.me":
        raise HTTPException(status_code=401, detail="Invalid LINE token issuer")
    if claims.get("aud") != channel_id:
        raise HTTPException(status_code=401, detail="Invalid LINE token audience")
    try:
        expires_at = int(claims.get("exp", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid LINE ID token") from exc
    if not claims.get("sub") or expires_at <= int(time()):
        raise HTTPException(status_code=401, detail="Expired LINE ID token")
    return AuthenticatedUser(subject=str(claims["sub"]), name=claims.get("name"))


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer LINE ID token required")
    return await verify_line_id_token(authorization[7:].strip())


def require_owner(path_user_id: str, current_user: AuthenticatedUser) -> str:
    if path_user_id != current_user.subject:
        raise HTTPException(status_code=403, detail="User ownership mismatch")
    return current_user.subject
