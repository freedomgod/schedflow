"""FastAPI application factory for SchedFlow.

The app binds a single :class:`~schedflow.core.scheduler.Scheduler`
instance and serves both the scheduling REST API (``/api``) and the
management API (``/api/v1``): components (executor/jobstore configuration),
SSE, authentication and settings.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from schedflow.configs.config import restore_component_configs
from schedflow.core.scheduler import STATE_STOPPED, Scheduler


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scheduler = app.state.scheduler
    # Bring the scheduler in line with the operator-configured timezone
    # before anything is armed or executed.
    from schedflow.api.timezone import apply_scheduler_timezone

    apply_scheduler_timezone(scheduler)
    # Restore previously persisted jobstores/executors before starting.
    restore_component_configs(scheduler)
    if scheduler.state == STATE_STOPPED:
        scheduler.start()
    from schedflow.core.webhook import WebhookEventSink
    from schedflow.settings.services import get_webhooks_config

    configs = get_webhooks_config()
    sink = WebhookEventSink(configs) if configs else None
    if sink is not None:
        sink.start(scheduler)
    app.state.webhook_sink = sink
    try:
        yield
    finally:
        if sink is not None:
            sink.close()
        scheduler.shutdown(wait=False)


def create_app(
    scheduler: Scheduler,
    include_routers: bool = True,
    include_exception_handlers: bool = True,
    include_auth: bool = True,
    **options: Any,
) -> FastAPI:
    """Create and configure the FastAPI application around one core scheduler."""
    from schedflow.utils.logging import configure_logging

    configure_logging()
    app = FastAPI(**options)
    app.state.scheduler = scheduler
    app.state.scheduler_api = scheduler
    app.router.lifespan_context = _lifespan

    if include_auth:
        from schedflow.api.middleware import AuthMiddleware
        from schedflow.auth.security import APIKeyBackend, JWTBackend

        app.add_middleware(
            AuthMiddleware,
            backends=[JWTBackend(), APIKeyBackend()],
        )

    from schedflow.api.middleware import (
        RateLimitMiddleware,
        TokenBucketLimiter,
    )
    from schedflow.settings.services import get_rate_limit_config

    rate_limiter = TokenBucketLimiter(get_rate_limit_config())
    app.state.rate_limiter = rate_limiter
    app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

    if include_routers:
        from schedflow.api.rest.routers import router as rest_router
        from schedflow.api.routers.auth import router as auth_router
        from schedflow.api.routers.components import router as components_router
        from schedflow.api.routers.settings import router as settings_router
        from schedflow.api.routers.sse import router as sse_router

        app.include_router(rest_router)
        app.include_router(components_router, prefix="/api/v1")
        app.include_router(sse_router, prefix="/api/v1")
        app.include_router(auth_router, prefix="/api/v1")
        app.include_router(settings_router, prefix="/api/v1")

    if include_exception_handlers:
        from schedflow.api.exceptions import register_exception_handlers

        register_exception_handlers(app)

    return app
