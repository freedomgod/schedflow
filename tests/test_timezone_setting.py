"""System default timezone: settings API, trigger fallback, scheduler wiring.

The scheduling stack used to resolve an omitted trigger timezone from the
process-local zone only, which is ``Etc/UTC`` in a container without ``TZ``.
These tests pin the replacement behaviour: an explicit trigger timezone wins,
otherwise the persisted system default applies, otherwise the process-local
zone is used.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from tzlocal import get_localzone

from schedflow.api import create_app
from schedflow.api.timezone import with_default_timezone
from schedflow.core import Scheduler
from schedflow.settings.services import get_default_timezone, set_timezone
from schedflow.triggers.cron import CronTrigger
from schedflow.triggers.interval import IntervalTrigger


def _client() -> TestClient:
    return TestClient(
        create_app(Scheduler(), include_auth=False),
        raise_server_exceptions=False,
    )


def _workflow_payload() -> dict:
    return {
        "flow_id": "tz",
        "nodes": [
            {
                "node_id": "a",
                "task": {"type": "python_callable", "ref": "os:getcwd"},
            }
        ],
        "edges": [],
    }


@pytest.fixture(autouse=True)
def _reset_timezone():
    """Never leak a configured timezone into other tests."""
    yield
    set_timezone(None)


# ── settings service ──────────────────────────────────

def test_default_timezone_falls_back_to_process_local_zone():
    assert get_default_timezone() == str(get_localzone())


def test_configured_timezone_wins_over_process_local_zone():
    set_timezone("Asia/Shanghai")
    assert get_default_timezone() == "Asia/Shanghai"


def test_invalid_timezone_is_rejected_by_the_service():
    with pytest.raises(ValueError, match="Mars/Phobos"):
        set_timezone("Mars/Phobos")


# ── settings API ──────────────────────────────────────

def test_get_timezone_reports_unset_system_default():
    with _client() as client:
        data = client.get("/api/v1/settings/timezone").json()["data"]

    assert data["timezone"] == str(get_localzone())
    assert data["configured"] is False
    assert "Asia/Shanghai" in data["available"]


def test_put_timezone_persists_and_reconfigures_live_scheduler():
    with _client() as client:
        resp = client.put(
            "/api/v1/settings/timezone", json={"timezone": "Asia/Shanghai"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["timezone"] == "Asia/Shanghai"
        assert resp.json()["data"]["configured"] is True

        assert client.app.state.scheduler.timezone == ZoneInfo("Asia/Shanghai")

        data = client.get("/api/v1/settings/timezone").json()["data"]
        assert data["timezone"] == "Asia/Shanghai"
        assert data["configured"] is True


def test_put_timezone_rejects_unknown_zone_with_clear_message():
    with _client() as client:
        resp = client.put(
            "/api/v1/settings/timezone", json={"timezone": "Mars/Phobos"}
        )

    assert resp.status_code == 422
    assert "Mars/Phobos" in resp.json()["detail"]


def test_put_null_timezone_restores_system_default():
    set_timezone("Asia/Shanghai")

    with _client() as client:
        resp = client.put("/api/v1/settings/timezone", json={"timezone": None})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert data["configured"] is False
        assert data["timezone"] == str(get_localzone())
        assert client.app.state.scheduler.timezone.utcoffset(
            datetime.now()
        ) == get_localzone().utcoffset(datetime.now())


def test_scheduler_uses_persisted_timezone_at_startup():
    set_timezone("Asia/Shanghai")

    with _client() as client:
        assert client.app.state.scheduler.timezone == ZoneInfo("Asia/Shanghai")


# ── trigger payload fallback ──────────────────────────

def test_cron_payload_without_timezone_gets_configured_default():
    set_timezone("Europe/Berlin")

    payload = with_default_timezone({"type": "cron", "args": {"hour": 9}})
    trigger = CronTrigger(**payload["args"])

    assert trigger.timezone == ZoneInfo("Europe/Berlin")
    assert trigger.to_dict()["args"]["timezone"] == "Europe/Berlin"


def test_interval_payload_without_timezone_gets_configured_default():
    set_timezone("Europe/Berlin")

    payload = with_default_timezone({"type": "interval", "args": {"seconds": 30}})
    trigger = IntervalTrigger(**payload["args"])

    assert trigger.to_dict()["args"]["timezone"] == "Europe/Berlin"


def test_explicit_timezone_in_payload_is_left_alone():
    set_timezone("Asia/Shanghai")

    payload = with_default_timezone(
        {"type": "cron", "args": {"hour": 9, "timezone": "Europe/Berlin"}}
    )

    assert payload["args"]["timezone"] == "Europe/Berlin"


def test_payload_of_type_without_timezone_argument_is_unchanged():
    set_timezone("Asia/Shanghai")

    payload = with_default_timezone({"type": "and", "args": {"jitter": 5}})

    assert payload == {"type": "and", "args": {"jitter": 5}}


def test_nested_combining_trigger_payload_gets_configured_default():
    set_timezone("Asia/Shanghai")

    payload = with_default_timezone(
        {
            "type": "or",
            "args": {
                "triggers": [
                    {"type": "cron", "args": {"hour": 9}},
                    {"type": "interval", "args": {"seconds": 30}},
                ]
            },
        }
    )

    nested = payload["args"]["triggers"]
    assert [item["args"]["timezone"] for item in nested] == [
        "Asia/Shanghai",
        "Asia/Shanghai",
    ]


# ── job creation paths ────────────────────────────────

def test_cron_job_created_without_timezone_uses_configured_default():
    set_timezone("Asia/Shanghai")

    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "cron", "args": {"hour": 9, "minute": 30}},
                "job_id": "tz-job",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

    assert data["trigger"]["args"]["timezone"] == "Asia/Shanghai"
    next_run = datetime.fromisoformat(data["next_run_time"])
    assert next_run.astimezone(ZoneInfo("Asia/Shanghai")).hour == 9
    assert next_run.astimezone(ZoneInfo("Asia/Shanghai")).minute == 30


def test_explicit_trigger_timezone_wins_over_configured_default():
    set_timezone("Asia/Shanghai")

    with _client() as client:
        resp = client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {
                    "type": "cron",
                    "args": {"hour": 9, "timezone": "Europe/Berlin"},
                },
                "job_id": "tz-explicit",
            },
        )
        assert resp.status_code == 200, resp.text

    assert resp.json()["data"]["trigger"]["args"]["timezone"] == "Europe/Berlin"


def test_reschedule_without_timezone_uses_configured_default():
    set_timezone("Asia/Shanghai")

    with _client() as client:
        client.post(
            "/api/jobs",
            json={
                "workflow": _workflow_payload(),
                "trigger": {"type": "interval", "args": {"hours": 1}},
                "job_id": "tz-reschedule",
            },
        )
        resp = client.post(
            "/api/v1/components/jobs/tz-reschedule/reschedule",
            json={"trigger": "cron", "trigger_args": {"hour": 7}},
        )
        assert resp.status_code == 200, resp.text
        job = client.get("/api/jobs/tz-reschedule").json()["data"]

    assert job["trigger"]["args"]["timezone"] == "Asia/Shanghai"
    next_run = datetime.fromisoformat(job["next_run_time"])
    assert next_run.astimezone(ZoneInfo("Asia/Shanghai")).hour == 7
