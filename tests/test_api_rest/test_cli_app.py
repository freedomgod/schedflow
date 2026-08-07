"""The CLI app binds a single core scheduler and starts it with the lifecycle."""
from fastapi.testclient import TestClient

from schedflow.cli import app
from schedflow.core.scheduler import STATE_RUNNING


def test_cli_app_uses_single_scheduler():
    assert app.state.scheduler is app.state.scheduler_api


def test_cli_app_lifespan_starts_scheduler():
    scheduler = app.state.scheduler
    with TestClient(app, raise_server_exceptions=False) as client:
        assert scheduler.state == STATE_RUNNING
        # /docs is behind auth middleware; just assert the app responds at all.
        assert client.get("/").status_code in (403, 404)
