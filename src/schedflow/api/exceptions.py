"""Exception handlers for the FastAPI application.

Maps domain exceptions to appropriate HTTP status codes and
:class:`~schedflow.api.schemas.APIResponse` bodies. Registered
handlers cover:

Status code mapping:
    404 — JobNotFoundError
    409 — JobConflictError, ValueError
    400 — LookupError
    500 — Unhandled exceptions (catch-all)
    502 — OSError (connection refused, timeout, DNS resolution)

Functions:
    register_exception_handlers — Install all handlers on a FastAPI app instance.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from schedflow.api.schemas import APIResponse
from schedflow.core.jobstore import JobConflictError, JobNotFoundError


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(JobNotFoundError)
    async def core_job_not_found_handler(request: Request, exc: JobNotFoundError):
        return JSONResponse(
            status_code=404,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )

    @app.exception_handler(JobConflictError)
    async def core_job_conflict_handler(request: Request, exc: JobConflictError):
        return JSONResponse(
            status_code=409,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=409,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )

    @app.exception_handler(LookupError)
    async def lookup_error_handler(request: Request, exc: LookupError):
        return JSONResponse(
            status_code=400,
            content=APIResponse(code=-1, message=str(exc)).model_dump(),
        )

    @app.exception_handler(OSError)
    async def os_error_handler(request: Request, exc: OSError):
        """Catch connection-level errors (refused, timeout, DNS resolution, etc.)."""
        return JSONResponse(
            status_code=502,
            content=APIResponse(code=-2, message=f"Upstream service unavailable: {exc}").model_dump(),
        )

    @app.exception_handler(Exception)
    async def fallback_exception_handler(request: Request, exc: Exception):
        """Catch-all handler to prevent unhandled exceptions from crashing the server."""
        import logging
        logger = logging.getLogger("schedflow.api")
        logger.exception("Unhandled exception in API request")
        return JSONResponse(
            status_code=500,
            content=APIResponse(code=-1, message=f"Internal server error: {exc}").model_dump(),
        )
