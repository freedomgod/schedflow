"""Authentication middleware for the FastAPI application.

AuthMiddleware intercepts every incoming request and validates credentials
before they reach route handlers. Requests to public paths (login, init
status/setup) are allowed through without authentication.

Classes:
    AuthMiddleware — Starlette-compatible ASGI middleware that iterates
        over a list of :class:`~schedflow.auth.security.AuthBackend`
        implementations, attaching the first successful
        :class:`~schedflow.auth.security.AuthResult` to
        ``request.state.auth``.
"""

import math
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from schedflow.api.schemas import APIResponse
from schedflow.auth.security import AuthBackend, AuthResult

PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/init-status",
    "/api/v1/auth/init-setup",
}

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class TokenBucketLimiter:
    """Thread-safe in-process token bucket keyed by client identity."""

    def __init__(self, config: dict) -> None:
        self._lock = threading.RLock()
        self._buckets: dict[str, tuple[float, float]] = {}
        self.reload(config)

    def reload(self, config: dict) -> None:
        with self._lock:
            self._enabled = bool(config.get("enabled", False))
            self._rpm = max(1, int(config.get("rpm", 120)))
            self._rate = self._rpm / 60.0
            self._buckets.clear()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def allow(self, key: str) -> tuple[bool, float]:
        with self._lock:
            now = time.monotonic()
            tokens, last = self._buckets.get(key, (float(self._rpm), now))
            tokens = min(self._rpm, tokens + (now - last) * self._rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            retry_after = (1.0 - tokens) / self._rate if self._rate else 60.0
            return False, retry_after


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply the limiter to write requests under ``/api/``."""

    def __init__(self, app, limiter: TokenBucketLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next):
        if (
            not self._limiter.enabled
            or request.method not in _WRITE_METHODS
            or not request.url.path.startswith("/api/")
        ):
            return await call_next(request)

        auth = getattr(request.state, "auth", None)
        subject = getattr(auth, "subject", None)
        client = request.client.host if request.client else "unknown"
        key = str(subject or client)
        allowed, retry_after = self._limiter.allow(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
                content=APIResponse(
                    code=-1, message="Too many requests"
                ).model_dump(),
            )
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, backends: list[AuthBackend]):
        super().__init__(app)
        self._backends = backends

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        for backend in self._backends:
            result: AuthResult = await backend.authenticate(request)
            if result.success:
                request.state.auth = result
                return await call_next(request)

        return JSONResponse(
            status_code=403,
            content=APIResponse(
                code=-1, message="Forbidden: invalid or missing credentials"
            ).model_dump(),
        )
