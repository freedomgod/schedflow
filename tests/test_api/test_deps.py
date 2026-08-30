"""TDD tests for dependency injection."""
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from schedflow.core import Scheduler


@pytest.fixture
def app():
    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler, include_auth=False)
    return app


def test_get_core_scheduler_is_valid_dependency(app):
    """get_core_scheduler should be a valid FastAPI dependency."""
    from schedflow.api.deps import get_core_scheduler

    app.add_api_route(
        "/test-dep", lambda s=Depends(get_core_scheduler): {"ok": True}
    )
    with TestClient(app) as client:
        resp = client.get("/test-dep")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


def test_get_core_scheduler_returns_correct_instance(app):
    """get_core_scheduler should return the core scheduler from app.state."""
    from schedflow.api.deps import get_core_scheduler

    app.add_api_route(
        "/test-scheduler",
        lambda s=Depends(get_core_scheduler): {"type": type(s).__name__},
    )
    with TestClient(app) as client:
        resp = client.get("/test-scheduler")
        assert resp.status_code == 200
        assert resp.json() == {"type": "Scheduler"}


def test_get_core_scheduler_is_same_instance(app):
    """get_core_scheduler should return the exact same instance stored in state."""
    from schedflow.api.deps import get_core_scheduler

    app.add_api_route(
        "/test-same",
        lambda s=Depends(get_core_scheduler): {"same": s is app.state.scheduler},
    )
    with TestClient(app) as client:
        resp = client.get("/test-same")
        assert resp.status_code == 200
        assert resp.json() == {"same": True}
