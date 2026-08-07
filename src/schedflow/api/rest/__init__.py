"""REST Web API built on the core Scheduler.

Endpoints mirror the SDK 1:1 and accept structured JSON (see
``api.rest.schemas``). The ``api`` package serves the management API of the
legacy scheduler; this package is the scheduling REST API for the core
objects.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from schedflow.api.rest import routers
from schedflow.api.schemas import APIResponse
from schedflow.configs.config import restore_component_configs
from schedflow.core.scheduler import STATE_STOPPED


def create_app(scheduler, **options) -> FastAPI:
    """Create a FastAPI app bound to a core :class:`Scheduler`."""
    app = FastAPI(**options)
    mount_routes(app, scheduler)
    return app


def mount_routes(app: FastAPI, scheduler) -> None:
    """Attach the REST API routes to an existing FastAPI app.

    The scheduler is stored as ``app.state.scheduler_api`` so a deployment
    that also serves the legacy management API (which uses
    ``app.state.scheduler``) can host both on a single app.
    """
    app.state.scheduler_api = scheduler
    app.include_router(routers.router)
    _register_exception_handlers(app)
    _bind_scheduler_lifespan(app, scheduler)


def _bind_scheduler_lifespan(app: FastAPI, scheduler) -> None:
    """Start the core scheduler with the app lifecycle and stop it on exit.

    Jobs added through ``POST /api/jobs`` live in this scheduler's job
    store. The legacy management app only starts ``app.state.scheduler`` in
    its own lifespan, so without this the core scheduler would stay stopped
    and jobs would be visible via the API but never executed.
    """
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        _restore_persisted_components(scheduler)
        if getattr(scheduler, "state", None) == STATE_STOPPED:
            scheduler.start()
        try:
            if original_lifespan is not None:
                async with original_lifespan(app):
                    yield
            else:
                yield
        finally:
            if getattr(scheduler, "state", None) != STATE_STOPPED:
                scheduler.shutdown(wait=False)

    app.router.lifespan_context = _lifespan


def _restore_persisted_components(scheduler) -> None:
    """Re-apply persisted executor/jobstore configs before the scheduler starts."""
    restore_component_configs(scheduler)


def _register_exception_handlers(app: FastAPI) -> None:
    from fastapi.responses import JSONResponse

    from schedflow.core.jobstore import JobConflictError, JobNotFoundError

    @app.exception_handler(JobNotFoundError)
    async def _not_found(request, exc: JobNotFoundError):
        return JSONResponse(
            status_code=404,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )

    @app.exception_handler(JobConflictError)
    async def _conflict(request, exc: JobConflictError):
        return JSONResponse(
            status_code=409,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )
