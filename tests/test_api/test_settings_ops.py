"""Webhook and rate-limit settings API tests."""

from fastapi.testclient import TestClient

from schedflow.api import create_app
from schedflow.core import Scheduler
from schedflow.settings.services import (
    get_rate_limit_config,
    get_webhooks_config,
    set_rate_limit_config,
    set_webhooks_config,
)


def _client() -> TestClient:
    return TestClient(
        create_app(Scheduler(), include_auth=False),
        raise_server_exceptions=False,
    )


def test_webhook_and_rate_limit_settings_roundtrip():
    try:
        with _client() as client:
            assert get_rate_limit_config()["enabled"] is False

            resp = client.put(
                "/api/v1/settings/rate-limit",
                json={"enabled": True, "rpm": 5},
            )
            assert resp.status_code == 200, resp.text
            assert get_rate_limit_config() == {"enabled": True, "rpm": 5}
            assert client.get(
                "/api/v1/settings/rate-limit"
            ).json()["data"] == {"enabled": True, "rpm": 5}

            resp = client.put(
                "/api/v1/settings/webhooks",
                json={
                    "webhooks": [
                        {
                            "url": "http://example.test/hook",
                            "events": ["job.*"],
                            "secret": "s",
                        }
                    ]
                },
            )
            assert resp.status_code == 200, resp.text
            assert get_webhooks_config() == [
                {
                    "url": "http://example.test/hook",
                    "events": ["job.*"],
                    "secret": "s",
                    "platform": "generic",
                }
            ]
    finally:
        set_rate_limit_config({"enabled": False, "rpm": 120})
        set_webhooks_config([])


def test_webhook_test_endpoint_requires_a_target():
    set_webhooks_config([])
    with _client() as client:
        response = client.post("/api/v1/settings/webhooks/test", json={})

    assert response.status_code == 422


def test_webhook_platform_is_persisted_and_validated():
    try:
        with _client() as client:
            resp = client.put(
                "/api/v1/settings/webhooks",
                json={
                    "webhooks": [
                        {
                            "url": "https://example.test/hook",
                            "events": ["job.failed"],
                            "platform": "dingtalk",
                        }
                    ]
                },
            )
            assert resp.status_code == 200, resp.text
            assert get_webhooks_config()[0]["platform"] == "dingtalk"

            unknown = client.put(
                "/api/v1/settings/webhooks",
                json={
                    "webhooks": [
                        {"url": "https://example.test/hook", "platform": "slack"}
                    ]
                },
            )
            assert unknown.status_code == 422, unknown.text
    finally:
        set_webhooks_config([])


def test_webhook_test_endpoint_forwards_the_platform(monkeypatch):
    import schedflow.core.webhook as webhook_module

    calls: dict = {}

    def fake_deliver_once(config, payload):
        calls["platform"] = config.platform
        return {
            "ok": True,
            "status_code": 200,
            "error": None,
            "duration_ms": 1.0,
            "platform": config.platform,
            "response": '{"errcode":0}',
        }

    monkeypatch.setattr(webhook_module, "deliver_once", fake_deliver_once)

    with _client() as client:
        response = client.post(
            "/api/v1/settings/webhooks/test",
            json={
                "url": "https://example.test/hook",
                "platform": "feishu",
                "secret": "s",
            },
        )

    assert response.status_code == 200, response.text
    assert calls["platform"] == "feishu"
    assert response.json()["data"]["platform"] == "feishu"


def test_webhook_test_endpoint_reports_delivery_result(monkeypatch):
    import schedflow.core.webhook as webhook_module

    calls: dict = {}

    def fake_deliver_once(config, payload):
        calls["url"] = config.url
        calls["payload"] = payload
        return {"ok": True, "status_code": 200, "error": None, "duration_ms": 1.0}

    monkeypatch.setattr(webhook_module, "deliver_once", fake_deliver_once)

    with _client() as client:
        response = client.post(
            "/api/v1/settings/webhooks/test",
            json={"url": "https://example.test/hook", "events": ["job.failed"]},
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["ok"] is True
    assert calls["url"] == "https://example.test/hook"
    assert calls["payload"]["kind"] == "job.failed"
    assert calls["payload"]["detail"] == {"source": "webhook-test"}
