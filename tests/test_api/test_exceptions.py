"""TDD tests for exception handlers (core exception mapping)."""
from fastapi.testclient import TestClient


def _make_app():
    from schedflow.api import create_app
    from schedflow.api.exceptions import register_exception_handlers
    from schedflow.core import Scheduler

    app = create_app(Scheduler(), include_auth=False)
    register_exception_handlers(app)

    @app.get("/test-not-found", include_in_schema=False)
    def raise_job_not_found():
        from schedflow.core.jobstore import JobNotFoundError

        raise JobNotFoundError("test-job-id")

    @app.get("/test-conflict", include_in_schema=False)
    def raise_conflicting_id():
        from schedflow.core.jobstore import JobConflictError

        raise JobConflictError("test-job-id")

    @app.get("/test-server-error", include_in_schema=False)
    def raise_generic():
        raise RuntimeError("something broke")

    @app.get("/test-value-error", include_in_schema=False)
    def raise_value_error():
        raise ValueError("bad input")

    return app


def test_job_not_found_returns_404():
    """JobNotFoundError should be converted to HTTP 404."""
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/test-not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == -1
        assert "test-job-id" in data["message"]


def test_job_conflict_returns_409():
    """JobConflictError should be converted to HTTP 409."""
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/test-conflict")
        assert resp.status_code == 409
        data = resp.json()
        assert data["code"] == -1


def test_generic_exception_returns_500():
    """Unhandled exceptions should return 500."""
    app = _make_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/test-server-error")
        assert resp.status_code == 500


def test_value_error_returns_409():
    """ValueError should be converted to HTTP 409."""
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/test-value-error")
        assert resp.status_code == 409
        data = resp.json()
        assert data["code"] == -1
