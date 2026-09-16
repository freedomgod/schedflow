"""The web API refuses trigger payloads that would fire continuously.

An empty cron matches every second and a zero interval keeps resolving to
"now"; both were reachable by submitting the job form without filling in the
trigger fields. The trigger classes keep their permissive semantics (pickling
re-validates partially populated models), so the guard lives at the API
boundary.
"""

import pytest
from fastapi.testclient import TestClient

from schedflow.api import create_app
from schedflow.api.trigger_validation import ensure_schedulable
from schedflow.core import Scheduler
from schedflow.exceptions.triggers import TriggerValidationError


def _client() -> TestClient:
    return TestClient(
        create_app(Scheduler(), include_auth=False),
        raise_server_exceptions=False,
    )


def _workflow_payload() -> dict:
    return {
        "flow_id": "guard",
        "nodes": [
            {
                "node_id": "a",
                "task": {"type": "python_callable", "ref": "os:getcwd"},
            }
        ],
        "edges": [],
    }


# ── unit level ────────────────────────────────────────

def test_empty_cron_is_rejected():
    with pytest.raises(TriggerValidationError, match="至少"):
        ensure_schedulable({"type": "cron", "args": {"timezone": "Asia/Shanghai"}})


def test_cron_with_only_blank_fields_is_rejected():
    with pytest.raises(TriggerValidationError, match="至少"):
        ensure_schedulable({"type": "cron", "args": {"hour": "", "minute": None}})


def test_explicit_every_second_cron_is_allowed():
    payload = {"type": "cron", "args": {"second": "*"}}

    assert ensure_schedulable(payload) is payload


def test_zero_interval_is_rejected():
    with pytest.raises(TriggerValidationError, match="大于 0"):
        ensure_schedulable({"type": "interval", "args": {"seconds": 0}})

    with pytest.raises(TriggerValidationError, match="大于 0"):
        ensure_schedulable({"type": "interval", "args": {}})


def test_positive_interval_is_allowed():
    payload = {"type": "interval", "args": {"minutes": 5}}

    assert ensure_schedulable(payload) is payload


def test_date_trigger_requires_a_run_date():
    with pytest.raises(TriggerValidationError, match="run_date"):
        ensure_schedulable({"type": "date", "args": {}})


def test_combining_trigger_validates_nested_triggers():
    with pytest.raises(TriggerValidationError, match="至少"):
        ensure_schedulable(
            {
                "type": "or",
                "args": {
                    "triggers": [
                        {"type": "cron", "args": {"hour": 9}},
                        {"type": "cron", "args": {}},
                    ]
                },
            }
        )


# ── API level ─────────────────────────────────────────

def test_api_rejects_a_cron_job_without_fields():
    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "cron", "args": {}},
                "job_id": "empty-cron",
            },
        )

    assert resp.status_code == 422, resp.text
    assert "Cron" in resp.json()["message"]


def test_api_rejects_a_zero_interval_job():
    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "interval", "args": {"seconds": 0}},
                "job_id": "zero-interval",
            },
        )

    assert resp.status_code == 422, resp.text
    assert "间隔" in resp.json()["message"]


def test_api_accepts_a_filled_in_cron_job():
    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "cron", "args": {"minute": "*/5"}},
                "job_id": "ok-cron",
            },
        )

    assert resp.status_code == 200, resp.text


def test_api_rejects_rescheduling_to_an_empty_cron():
    with _client() as client:
        client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "interval", "args": {"hours": 1}},
                "job_id": "reschedule-guard",
            },
        )
        resp = client.post(
            "/api/v1/components/jobs/reschedule-guard/reschedule",
            json={"trigger": "cron", "trigger_args": {}},
        )

    assert resp.status_code == 422, resp.text
