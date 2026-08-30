"""TDD tests for component management API endpoints."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from schedflow.configs.config import remove_jobstore_config

FUTURE_RUN_TIME = (datetime.now() + timedelta(days=365)).isoformat()


def _make_app():
    from schedflow.api.exceptions import register_exception_handlers
    from schedflow.api.rest import create_app
    from schedflow.core import Scheduler

    scheduler = Scheduler()
    app = create_app(scheduler, title="components-test")
    register_exception_handlers(app)

    from schedflow.api.routers.components import router as comp_router
    app.include_router(comp_router, prefix="/api/v1")

    return app


class TestTriggerListing:
    def test_list_triggers(self):
        """GET /api/v1/components/triggers should list available trigger types."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/triggers")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)
            trigger_names = [t["name"] for t in data["data"]]
            assert "date" in trigger_names
            assert "interval" in trigger_names
            assert "cron" in trigger_names


class TestReschedule:
    def test_reschedule_job(self):
        """POST /api/v1/components/jobs/{job_id}/reschedule should reschedule."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            # Add a job first
            add_resp = client.post("/api/jobs", json={
                "workflow": {
                    "nodes": [{
                        "node_id": "a",
                        "task": {"type": "python_callable", "ref": "math:sqrt"},
                        "name": "task-a",
                    }],
                    "edges": [],
                },
                "trigger": {"type": "date", "args": {"run_date": FUTURE_RUN_TIME}},
            })
            assert add_resp.status_code == 200, add_resp.text
            job_id = add_resp.json()["data"]["job_id"]

            resp = client.post(
                f"/api/v1/components/jobs/{job_id}/reschedule",
                json={"trigger": "interval", "trigger_args": {"seconds": 60}},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0

    def test_reschedule_nonexistent_job_returns_404(self):
        """POST reschedule for nonexistent job should return 404."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/v1/components/jobs/nonexistent/reschedule",
                json={"trigger": "interval", "trigger_args": {"seconds": 60}},
            )
            assert resp.status_code == 404


class TestExecutorListing:
    def test_list_executors(self):
        """GET /api/v1/components/executors should list available executor types."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/executors")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)


class TestJobStoreListing:
    def test_list_jobstores(self):
        """GET /api/v1/components/jobstores should list available jobstore types."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/jobstores")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)


class TestGetJobstoreConfig:
    def test_get_configured_jobstore(self, tmp_path):
        """GET /components/jobstores/configured/{alias} should return config."""
        db_url = f"sqlite:///{tmp_path.as_posix()}/test.db"
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/api/v1/components/jobstores/configure/teststore", json={
                "type": "sqlalchemy",
                "config": {"url": db_url},
            })
            resp = client.get("/api/v1/components/jobstores/configured/teststore")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert data["data"]["alias"] == "teststore"
            assert data["data"]["type"] == "sqlalchemy"
            assert data["data"]["config"]["url"] == db_url

    def test_get_nonexistent_jobstore_returns_404(self):
        """GET configured jobstore for nonexistent alias should return 404."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/jobstores/configured/nonexistent")
            assert resp.status_code == 404

    def teardown_method(self):
        try:
            remove_jobstore_config("teststore")
        except Exception:  # noqa: BLE001, S110 - best-effort cleanup
            pass


class TestGetExecutorsConfigured:
    def test_list_configured_executors(self):
        """GET /components/executors/configured should return configured executors."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/components/executors/configured")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert isinstance(data["data"], list)
            assert len(data["data"]) > 0
            assert "name" in data["data"][0]
            assert "type" in data["data"][0]
            aliases = [e["alias"] for e in data["data"]]
            assert "default" in aliases


class TestConfiguredListsIncludeDefaults:
    def test_configured_lists_include_default_components(self):
        """Both configured lists read persisted configs and include defaults."""
        app = _make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            exec_resp = client.get("/api/v1/components/executors/configured")
            store_resp = client.get("/api/v1/components/jobstores/configured")
            assert exec_resp.status_code == 200
            assert store_resp.status_code == 200
            exec_aliases = [e["alias"] for e in exec_resp.json()["data"]]
            store_aliases = [s["alias"] for s in store_resp.json()["data"]]
            assert "default" in exec_aliases
            assert "default" in store_aliases
            assert len(exec_resp.json()["data"]) == 1
            assert len(store_resp.json()["data"]) == 1
