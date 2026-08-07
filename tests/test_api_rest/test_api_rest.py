"""REST Web API tests."""

import time

from fastapi.testclient import TestClient

from schedflow.api.rest import create_app
from schedflow.core.executor import DebugExecutor
from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.scheduler import STATE_RUNNING, Scheduler


def make_client() -> TestClient:
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=DebugExecutor())
    app = create_app(scheduler, title="Scheduler API")
    return TestClient(app)


def workflow_payload(flow_id: str = "wf") -> dict:
    return {
        "flow_id": flow_id,
        "nodes": [
            {
                "node_id": "a",
                "task": {"type": "python_callable", "ref": "os:getcwd"},
                "name": "task-a",
            }
        ],
        "edges": [],
    }


def test_create_job_with_workflow_and_trigger():
    client = make_client()
    response = client.post(
        "/api/jobs",
        json={
            "workflow": workflow_payload(),
            "trigger": {"type": "interval", "args": {"seconds": 60}},
            "job_id": "j1",
            "name": "my job",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["job_id"] == "j1"
    assert data["name"] == "my job"
    assert data["trigger"]["type"] == "interval"


def test_create_job_accepts_string_task():
    client = make_client()
    payload = workflow_payload()
    payload["nodes"][0]["task"] = "os:getcwd"
    response = client.post(
        "/api/jobs", json={"workflow": payload, "job_id": "j1"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["job_id"] == "j1"


def test_create_job_unknown_ref_is_accepted():
    client = make_client()
    payload = workflow_payload()
    payload["nodes"][0]["task"]["ref"] = "missing_module_xyz:fn"
    response = client.post(
        "/api/jobs", json={"workflow": payload, "job_id": "j1"}
    )
    assert response.status_code == 200, response.text


def test_create_job_unknown_trigger_type_422():
    client = make_client()
    response = client.post(
        "/api/jobs",
        json={
            "workflow": workflow_payload(),
            "trigger": {"type": "nope", "args": {}},
        },
    )
    assert response.status_code == 422


def test_create_job_cycle_422():
    client = make_client()
    payload = workflow_payload()
    payload["nodes"].append(
        {
            "node_id": "b",
            "task": {"type": "python_callable", "ref": "os:getcwd"},
        }
    )
    payload["edges"] = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "a"},
    ]
    response = client.post(
        "/api/jobs", json={"workflow": payload}
    )
    assert response.status_code == 422


def test_create_job_missing_node_edge_422():
    client = make_client()
    payload = workflow_payload()
    payload["edges"] = [{"source": "a", "target": "ghost"}]
    response = client.post(
        "/api/jobs", json={"workflow": payload}
    )
    assert response.status_code == 422


def test_list_and_get_job():
    client = make_client()
    client.post("/api/jobs", json={"workflow": workflow_payload(), "job_id": "j1"})
    jobs = client.get("/api/jobs").json()["data"]
    assert [job["job_id"] for job in jobs] == ["j1"]
    job = client.get("/api/jobs/j1").json()["data"]
    assert job["job_id"] == "j1"


def test_get_missing_job_404():
    client = make_client()
    response = client.get("/api/jobs/missing")
    assert response.status_code == 404


def test_update_job():
    client = make_client()
    client.post("/api/jobs", json={"workflow": workflow_payload(), "job_id": "j1"})
    response = client.put(
        "/api/jobs/j1", json={"name": "renamed", "max_instances": 3}
    )
    assert response.status_code == 200
    assert client.get("/api/jobs/j1").json()["data"]["name"] == "renamed"
    assert client.get("/api/jobs/j1").json()["data"]["max_instances"] == 3


def test_delete_job():
    client = make_client()
    client.post("/api/jobs", json={"workflow": workflow_payload(), "job_id": "j1"})
    assert client.delete("/api/jobs/j1").status_code == 200
    assert client.get("/api/jobs/j1").status_code == 404


def test_pause_resume_run_and_logs():
    client = make_client()
    client.post(
        "/api/jobs",
        json={"workflow": workflow_payload(), "job_id": "j1"},
    )
    assert client.post("/api/jobs/j1/pause").status_code == 200
    assert client.get("/api/jobs/j1").json()["data"]["next_run_time"] is None
    assert client.post("/api/jobs/j1/resume").status_code == 200

    run_response = client.post("/api/jobs/j1/run")
    assert run_response.status_code == 200, run_response.text
    log_id = run_response.json()["data"]["log_id"]

    logs = client.get("/api/jobs/j1/logs").json()["data"]
    assert [log["log_id"] for log in logs] == [log_id]
    detail = client.get(f"/api/jobs/j1/logs/{log_id}").json()["data"]
    assert detail["records"]["a"]["status"] == "succeeded"


def test_scheduler_status_and_controls():
    client = make_client()
    status = client.get("/api/scheduler/status").json()["data"]
    assert status["state_name"] == "STOPPED"
    assert client.post("/api/scheduler/start").status_code == 200
    assert client.post("/api/scheduler/pause").status_code == 200
    assert client.post("/api/scheduler/resume").status_code == 200
    assert client.post("/api/scheduler/shutdown").status_code == 200


def test_lifespan_starts_scheduler_and_executes_due_jobs():
    """The app lifespan must start the bound core scheduler.

    Jobs added through ``POST /api/jobs`` live in the core scheduler's job
    store; if that scheduler is never started, jobs are visible via the API
    but its main loop never executes them.
    """
    scheduler = Scheduler(jobstore=MemoryJobStore(), executor=DebugExecutor())
    app = create_app(scheduler, title="Scheduler API")

    with TestClient(app) as client:
        assert scheduler.state == STATE_RUNNING, (
            "REST app lifespan must start the core scheduler"
        )

        # A trigger dated in the past should be picked up as due by the loop.
        response = client.post(
            "/api/jobs",
            json={
                "workflow": workflow_payload(),
                "job_id": "j1",
                "trigger": {"type": "date", "args": {"run_date": "2020-01-01 00:00:00"}},
            },
        )
        assert response.status_code == 200, response.text

        deadline = time.monotonic() + 5
        logs = []
        while time.monotonic() < deadline:
            logs = scheduler.get_job_logs("j1")
            if logs:
                break
            time.sleep(0.05)
        assert logs, "due job should have been executed by the scheduler loop"
