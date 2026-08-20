"""Auth helpers (anonymous site JWT — separate from appointment cancel codes)."""
from __future__ import annotations

import secrets
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import JWT_ALGORITHM, JWT_AUDIENCE, JWT_EXPIRE_MINUTES, JWT_SECRET

security = HTTPBearer()


def _require_secret() -> None:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET is not set. Add a strong secret to .env.",
        )


def new_session_id() -> str:
    """Cryptographically random anonymous session id."""
    return secrets.token_urlsafe(32)


def thread_id_for_sid(sid: str) -> str:
    """Derive LangGraph thread_id from JWT sid (server-owned; not client-chosen)."""
    sid_n = (sid or "").strip()
    if not sid_n:
        raise HTTPException(status_code=401, detail="Invalid session")
    return f"chat:{sid_n}"


def create_access_token(sid: str | None = None) -> dict[str, Any]:
    """Issue an anonymous session JWT. Returns token fields for the API response."""
    _require_secret()
    sid_n = (sid or "").strip() or new_session_id()
    now = int(time.time())
    expires_in = max(1, int(JWT_EXPIRE_MINUTES)) * 60
    exp = now + expires_in
    payload = {
        "sub": "anonymous-chat",
        "sid": sid_n,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "sid": sid_n,
        "expires_in": expires_in,
        "expires_at": exp,
    }


def decode_access_token(token: str) -> dict[str, Any]:
    _require_secret()
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None


def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Validate Bearer JWT and return claims (must include sid)."""
    claims = decode_access_token(credentials.credentials)
    sid = str(claims.get("sid") or "").strip()
    if not sid:
        raise HTTPException(status_code=401, detail="Invalid session")
    return claims


def refresh_access_token(token: str) -> dict[str, Any]:
    """Re-issue JWT for the same sid while the current token is still valid."""
    claims = decode_access_token(token)
    sid = str(claims.get("sid") or "").strip()
    if not sid:
        raise HTTPException(status_code=401, detail="Invalid session")
    return create_access_token(sid=sid)
