"""Owner dashboard JWT and password helpers (separate from anonymous widget auth)."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import (
    JWT_ALGORITHM,
    JWT_SECRET,
    OWNER_JWT_AUDIENCE,
    OWNER_JWT_EXPIRE_MINUTES,
)

security = HTTPBearer()
MIN_PASSWORD_LENGTH = 10


def _require_secret() -> None:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="JWT_SECRET is not set. Add a strong secret to .env.",
        )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            (password_hash or "").encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def hash_opaque_token(raw: str) -> str:
    """SHA-256 hash for email codes / reset tokens (not passwords)."""
    return hashlib.sha256((raw or "").strip().encode("utf-8")).hexdigest()


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def create_owner_token(
    *,
    owner_id: int,
    username: str,
    setup_completed: bool,
) -> dict[str, Any]:
    _require_secret()
    now = int(time.time())
    # Shorter session while onboarding is incomplete.
    minutes = 30 if not setup_completed else max(1, int(OWNER_JWT_EXPIRE_MINUTES))
    expires_in = minutes * 60
    exp = now + expires_in
    payload = {
        "sub": "owner",
        "uid": int(owner_id),
        "username": username,
        "setup_completed": bool(setup_completed),
        "aud": OWNER_JWT_AUDIENCE,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "expires_at": exp,
        "setup_completed": bool(setup_completed),
        "setup_required": not bool(setup_completed),
        "username": username,
    }


def decode_owner_token(token: str) -> dict[str, Any]:
    _require_secret()
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=OWNER_JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired owner token") from None


def verify_owner_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    claims = decode_owner_token(credentials.credentials)
    if claims.get("sub") != "owner" or not claims.get("uid"):
        raise HTTPException(status_code=401, detail="Invalid owner token")
    return claims


def require_owner_setup_pending(claims: dict[str, Any] = Depends(verify_owner_jwt)) -> dict[str, Any]:
    if claims.get("setup_completed"):
        raise HTTPException(status_code=400, detail="Setup already completed")
    return claims


def require_owner_ready(claims: dict[str, Any] = Depends(verify_owner_jwt)) -> dict[str, Any]:
    if not claims.get("setup_completed"):
        raise HTTPException(
            status_code=403,
            detail="Complete owner setup before using the dashboard",
        )
    return claims


def validate_new_password(password: str) -> str:
    pw = password or ""
    if len(pw) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    return pw
