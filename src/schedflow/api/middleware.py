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
