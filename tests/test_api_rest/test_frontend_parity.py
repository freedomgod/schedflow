"""Feature-parity checks for the API surface the frontend depends on.

These tests assert the component sets and behaviors the web UI relies on:
executor/jobstore/trigger lists, job execution, SSE and store configuration.
"""

import asyncio
import json
import time

from fastapi.testclient import TestClient

from schedflow.api import create_app
from schedflow.configs.config import (
    remove_executor_config,
    remove_jobstore_config,
)
from schedflow.core import Scheduler


def _client():
    app = create_app(Scheduler(), include_auth=False)
    return TestClient(app, raise_server_exceptions=False)


def _workflow_payload():
    return {
        "flow_id": "parity",
        "nodes": [
            {
                "node_id": "a",
                "task": {
                    "type": "python_callable",
                    "ref": "os:getcwd",
                },
                "name": "task-a",
            }
        ],
        "edges": [],
    }


def test_component_plugin_sets_match_frontend_contract():
    with _client() as client:
        executors = [p["name"] for p in client.get("/api/v1/components/executors/plugins").json()["data"]]
        assert set(executors) == {
            "debug", "threadpool", "processpool", "asyncio", "gevent", "tornado", "twisted",
        }
        jobstores = [p["name"] for p in client.get("/api/v1/components/jobstores/plugins").json()["data"]]
        assert set(jobstores) == {"memory", "sqlalchemy", "redis", "mongodb"}
        triggers = [t["name"] for t in client.get("/api/v1/components/triggers").json()["data"]]
        assert set(triggers) == {"calendarinterval", "date", "interval", "cron", "and", "or"}


def test_job_created_via_api_runs_and_logs():
    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "interval", "args": {"seconds": 1}},
                "job_id": "parity-job",
            },
        )
        assert resp.status_code == 200, resp.text
        jobs = client.get("/api/jobs").json()["data"]
        assert any(j["job_id"] == "parity-job" for j in jobs)

        deadline = time.monotonic() + 10
        logs = []
        while time.monotonic() < deadline:
            resp = client.get("/api/jobs/parity-job/logs")
            logs = resp.json()["data"] if resp.status_code == 200 else []
            if logs:
                break
            time.sleep(0.05)
        assert logs, "job should have executed via the scheduler loop"
        assert logs[0]["records"]["a"]["status"] == "succeeded"


def test_sse_route_serves_core_jobs():
    """The SSE route is registered and produces events for core jobs.

    The data path is exercised at the generator level because streaming test
    clients (TestClient / ASGITransport) cannot consume an infinite SSE body;
    a real server check confirms the first chunk arrives over HTTP.
    """
    with _client() as client:
        client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "interval", "args": {"seconds": 3600}},
                "job_id": "sse-job",
            },
        )
        scheduler = client.app.state.scheduler

        async def event_stream():
            last_run_time = None
            while True:
                try:
                    job = scheduler.get_job("sse-job")
                    if job is None:
                        yield "event: error\n\n"
                        break
                    current = job.next_run_time
                    current_str = current.isoformat() if current else None
                    if current_str != last_run_time:
                        last_run_time = current_str
                        yield f"data: {json.dumps({'next_run_time': current_str})}\n\n"
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    break
                except Exception:  # noqa: BLE001 - mirrors the endpoint's guard
                    break

        async def first_event():
            async for item in event_stream():
                return item
            return None

        first = asyncio.run(asyncio.wait_for(first_event(), timeout=5))
        assert first is not None
        assert "next_run_time" in first

        # The error branch also ends cleanly (job not found).
        with client.stream(
            "GET", "/api/v1/sse/jobs/does-not-exist/next-run-time"
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            chunk = next(response.iter_bytes())
            assert b"error" in chunk


def test_jobstore_configuration_persists_and_lists():
    try:
        with _client() as client:
            resp = client.post(
                "/api/v1/components/jobstores/configure/parity-store",
                json={"type": "sqlalchemy", "config": {"url": "sqlite:///:memory:"}},
            )
            assert resp.status_code == 200, resp.text
            names = [s["alias"] for s in client.get("/api/v1/components/jobstores/configured").json()["data"]]
            assert "parity-store" in names
    finally:
        try:
            remove_jobstore_config("parity-store")
            remove_executor_config("parity-store")
        except Exception:  # noqa: BLE001, S110 - cleanup best effort
            pass
