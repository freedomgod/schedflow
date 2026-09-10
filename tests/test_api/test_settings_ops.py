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
                }
            ]
    finally:
        set_rate_limit_config({"enabled": False, "rpm": 120})
        set_webhooks_config([])
