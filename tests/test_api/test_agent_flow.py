"""Exercise the actual HTTP/core chain without an external model service."""

import json
import time

from fastapi import Request
from fastapi.testclient import TestClient

from schedflow.agent import AgentConfig, AgentService
from schedflow.api import create_app
from schedflow.auth.security import AuthResult
from schedflow.core import Scheduler


class WorkflowProvider:
    async def stream(self, messages, tools):
        if messages[-1]["role"] == "tool":
            yield {"type": "text", "text": "草案已准备，请检查后确认。"}
            return
        text = messages[-1]["content"]
        if text.startswith("run "):
            name = "propose_run_workflow"
            arguments = {"job_id": text.removeprefix("run ")}
        elif text.startswith("update "):
            name = "propose_update_workflow"
            arguments = {
                "job_id": text.removeprefix("update "),
                "payload": {"name": "changed"},
            }
        else:
            name = "propose_create_workflow"
            arguments = {
                "payload": {
                    "name": "two nodes",
                    "workflow": {
                        "nodes": [
                            {
                                "node_id": "first",
                                "task": {
                                    "type": "python_callable",
                                    "ref": "operator:neg",
                                    "args": [42],
                                },
                            },
                            {
                                "node_id": "second",
                                "task": {
                                    "type": "python_callable",
                                    "ref": "operator:neg",
                                    "args": [43],
                                },
                            },
                        ],
                        "edges": [{"source": "first", "target": "second"}],
                    },
                }
            }
        yield {
            "type": "tool_call",
            "id": "call",
            "name": name,
            "arguments": json.dumps(arguments),
        }


def wait_turn(client, session_id, message):
    base = "/api/v1/agent"
    response = client.post(
        f"{base}/sessions/{session_id}/turns", json={"message": message}
    )
    assert response.status_code == 200, response.text
    turn_id = response.json()["data"]["turn_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        turn = client.get(f"{base}/turns/{turn_id}").json()["data"]
        if turn["status"] not in {"queued", "running"}:
            assert turn["status"] == "completed", turn
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Turn did not finish")
    return client.get(f"{base}/sessions/{session_id}").json()["data"]["proposals"][-1]


def test_http_proposal_confirm_update_run_and_recover():
    scheduler = Scheduler()
    service = AgentService(
        scheduler,
        provider=WorkflowProvider(),
        config=AgentConfig(
            enabled=True, model="offline-test", allow_code_generation=True
        ),
    )
    app = create_app(scheduler, include_auth=False, agent_service=service)

    @app.middleware("http")
    async def actor(request: Request, call_next):
        request.state.auth = AuthResult(True, "offline-user", "jwt")
        return await call_next(request)

    base = "/api/v1/agent"
    with TestClient(app) as client:
        session_id = client.post(base + "/sessions", json={}).json()["data"][
            "session_id"
        ]
        proposal = wait_turn(client, session_id, "create")
        snapshot = client.get(f"{base}/sessions/{session_id}").json()["data"]
        turn_id = snapshot["turns"][-1]["turn_id"]
        stream = client.get(f"{base}/turns/{turn_id}/events")
        assert stream.status_code == 200
        events = [
            json.loads(line[6:])
            for line in stream.text.splitlines()
            if line.startswith("data: ")
        ]
        assert events[-1]["type"] == "turn.completed"
        assert all(event["turn_id"] == turn_id for event in events)
        cursor = events[-1]["seq"]
        assert (
            "data:"
            not in client.get(
                f"{base}/turns/{turn_id}/events", params={"after": cursor}
            ).text
        )
        assert not scheduler.get_jobs(), "Preview must not mutate scheduler"
        confirmation = {"proposal_version": proposal["version"]}
        url = f"{base}/proposals/{proposal['proposal_id']}/approve"
        created = client.post(url, json=confirmation).json()["data"]
        assert created["status"] == "succeeded"
        assert (
            client.post(url, json=confirmation).json()["data"]["operation_id"]
            == created["operation_id"]
        )
        job_id = created["job_id"]
        assert scheduler.get_job(job_id).status == "paused"
        proposal = wait_turn(client, session_id, "update " + job_id)
        assert scheduler.get_job(job_id).name == "two nodes"
        updated = client.post(
            f"{base}/proposals/{proposal['proposal_id']}/approve",
            json={"proposal_version": proposal["version"]},
        )
        assert updated.status_code == 200, updated.text
        assert scheduler.get_job(job_id).name == "changed"
        proposal = wait_turn(client, session_id, "run " + job_id)
        accepted = client.post(
            f"{base}/proposals/{proposal['proposal_id']}/approve",
            json={"proposal_version": proposal["version"]},
        ).json()["data"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            operation = client.get(
                f"{base}/operations/{accepted['operation_id']}"
            ).json()["data"]
            if operation["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert operation["status"] == "succeeded", operation
        assert operation["result"]["log_id"] == accepted["execution_id"]
        assert set(operation["result"]["records"]) == {"first", "second"}
        restored = client.get(f"{base}/sessions/{session_id}").json()["data"]
        assert any(
            block["type"] == "execution"
            for message in restored["messages"]
            for block in message["blocks"]
        )
