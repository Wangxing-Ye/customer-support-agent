"""In-process sliding-window rate limits (phase 1; single-process only)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from backend.config import (
    AUTH_REFRESH_PER_MINUTE,
    AUTH_TOKEN_PER_HOUR,
    AUTH_TOKEN_PER_MINUTE,
    TRUST_PROXY_HEADERS,
)

_lock = threading.Lock()
# key → deque of monotonic timestamps
_hits: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    """Best-effort client IP. Only trust X-Forwarded-For when behind a known proxy."""
    if TRUST_PROXY_HEADERS:
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            # Leftmost is the original client when proxies append.
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune(q: deque[float], now: float, window_seconds: float) -> None:
    cutoff = now - window_seconds
    while q and q[0] < cutoff:
        q.popleft()


def check_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: float,
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds). On allow, records the hit."""
    if limit <= 0:
        return True, 0
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        _prune(q, now, window_seconds)
        if len(q) >= limit:
            retry = max(1, int(window_seconds - (now - q[0])) + 1)
            return False, retry
        q.append(now)
        return True, 0


def enforce_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: float,
    detail: str = "Rate limit exceeded. Try again later.",
) -> None:
    allowed, retry_after = check_rate_limit(
        key=key, limit=limit, window_seconds=window_seconds
    )
    if allowed:
        return
    raise HTTPException(
        status_code=429,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


def enforce_auth_token_limits(request: Request) -> str:
    """Apply per-IP minute + hour caps for POST /auth/token. Returns client IP."""
    ip = client_ip(request)
    enforce_rate_limit(
        key=f"auth:token:m:{ip}",
        limit=AUTH_TOKEN_PER_MINUTE,
        window_seconds=60,
        detail="Too many token requests. Try again in a minute.",
    )
    enforce_rate_limit(
        key=f"auth:token:h:{ip}",
        limit=AUTH_TOKEN_PER_HOUR,
        window_seconds=3600,
        detail="Too many token requests this hour. Try again later.",
    )
    return ip


def enforce_auth_refresh_limits(*, sid: str, request: Request) -> None:
    """Per-sid (and light per-IP) caps for POST /auth/refresh."""
    sid_n = (sid or "").strip() or "unknown"
    ip = client_ip(request)
    enforce_rate_limit(
        key=f"auth:refresh:sid:{sid_n}",
        limit=AUTH_REFRESH_PER_MINUTE,
        window_seconds=60,
        detail="Too many refresh requests. Try again in a minute.",
    )
    # Soft IP cap so rotating sids cannot amplify forever from one host.
    enforce_rate_limit(
        key=f"auth:refresh:ip:{ip}",
        limit=max(AUTH_REFRESH_PER_MINUTE * 3, 60),
        window_seconds=60,
        detail="Too many refresh requests from this network. Try again in a minute.",
    )
