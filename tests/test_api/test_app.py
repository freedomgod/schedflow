"""TDD tests for create_app factory (unified core scheduler app)."""
import pytest
from fastapi.testclient import TestClient

from schedflow.core import Scheduler
from schedflow.core.scheduler import STATE_RUNNING, STATE_STOPPED


def test_create_app_exists():
    """create_app should be importable from schedflow.api."""


def test_create_app_returns_fastapi_app():
    """create_app(scheduler) should return a FastAPI instance."""
    from fastapi import FastAPI

    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler)
    assert isinstance(app, FastAPI)


def test_create_app_stores_scheduler_in_state():
    """The scheduler should be accessible from app.state.scheduler."""
    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler)
    assert app.state.scheduler is scheduler
    assert app.state.scheduler_api is scheduler


@pytest.mark.anyio
async def test_lifespan_starts_and_shuts_down_scheduler():
    """Lifespan should start scheduler on enter and shutdown on exit."""
    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler)
    assert scheduler.state == STATE_STOPPED

    async with app.router.lifespan_context(app):
        assert scheduler.state == STATE_RUNNING

    assert scheduler.state == STATE_STOPPED


def test_create_app_accepts_title_option():
    """create_app should pass through FastAPI options like title."""
    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler, title="Test API")
    assert app.title == "Test API"


@pytest.mark.anyio
async def test_testclient_with_lifespan():
    """TestClient as context manager should trigger lifespan events."""
    from schedflow.api import create_app

    scheduler = Scheduler()
    app = create_app(scheduler, include_auth=False)

    assert scheduler.state == STATE_STOPPED
    with TestClient(app, raise_server_exceptions=False) as client:
        assert scheduler.state == STATE_RUNNING
        resp = client.get("/docs")
        assert resp.status_code == 200

    assert scheduler.state == STATE_STOPPED


class TestCreateAppAutoRegister:
    def test_auto_register_routers(self):
        """create_app should auto-register the REST and management routers."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/jobs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)

    def test_auto_register_triggers_endpoint(self):
        """auto-registered app should expose /api/v1/components/triggers."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/triggers")
            assert resp.status_code == 200
            data = resp.json()
            trigger_names = [t["name"] for t in data["data"]]
            assert "date" in trigger_names

    def test_auto_register_scheduler_status_endpoint(self):
        """auto-registered app should expose /api/scheduler/status."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/scheduler/status")
            assert resp.status_code == 200
            assert "state" in resp.json()["data"]

    def test_auto_register_logs_endpoint(self):
        """auto-registered app should expose /api/jobs/{id}/logs."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/jobs/nonexistent/logs")
            assert resp.status_code == 404

    def test_include_routers_false_skips_registration(self):
        """create_app(include_routers=False) should skip router registration."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_routers=False, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/jobs")
            assert resp.status_code == 404

    def test_auto_register_exception_handlers(self):
        """create_app with defaults should register exception handlers."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(scheduler, include_auth=False)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/jobs/nonexistent-job-id")
            assert resp.status_code == 404
            data = resp.json()
            assert data["code"] == -1

    def test_include_exception_handlers_false_skips_registration(self):
        """create_app(include_exception_handlers=False) should skip handlers."""
        from schedflow.api import create_app

        scheduler = Scheduler()
        app = create_app(
            scheduler,
            include_exception_handlers=False,
            include_routers=False,
            include_auth=False,
        )

        from schedflow.api.rest.routers import router

        app.include_router(router)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/jobs/nonexistent-job-id")
            assert resp.status_code == 500
