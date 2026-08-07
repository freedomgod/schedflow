"""FastAPI dependency injection utilities.

Provides reusable dependencies for route handlers so they can access
shared application state without coupling to the request lifecycle.

Functions:
    get_core_scheduler — Inject the core :class:`~schedflow.core.scheduler.Scheduler`
        instance attached to the FastAPI app.
    get_current_user — Inject the authenticated user identity from
        :class:`~schedflow.auth.security.AuthResult`.
"""

from fastapi import Request

from schedflow.auth.security import AuthResult
from schedflow.core.scheduler import Scheduler


def get_core_scheduler(request: Request) -> Scheduler:
    """Return the core scheduler bound to the app."""
    scheduler = getattr(request.app.state, "scheduler_api", None)
    if scheduler is None:
        scheduler = getattr(request.app.state, "scheduler", None)
    return scheduler


def get_current_user(request: Request) -> AuthResult:
    return request.state.auth
