"""TDD tests for auth middleware."""
import pytest
from fastapi import Request
from fastapi.testclient import TestClient


def _make_app():
    from schedflow.api import create_app
    from schedflow.core import Scheduler

    app = create_app(Scheduler(), include_auth=False)

    @app.get("/protected", include_in_schema=False)
    def dummy_protected():
        return {"ok": True}

    return app


class TestAPIKeyBackend:
    def test_no_api_key_returns_403(self):
        """Requests without API key should return 403."""
        from schedflow.api.middleware import AuthMiddleware
        from schedflow.auth.security import AuthBackend, AuthResult

        class FixedKeyBackend(AuthBackend):
            def __init__(self, api_key: str = ""):
                self._api_key = api_key

            async def authenticate(self, request: Request):
                key = request.headers.get("X-API-Key", "")
                if key and key == self._api_key:
                    return AuthResult(success=True, user_id="test", method="apikey")
                return AuthResult(success=False)

        app = _make_app()
        backend = FixedKeyBackend(api_key="secret-token")
        app.add_middleware(AuthMiddleware, backends=[backend])

        with TestClient(app) as client:
            resp = client.get("/protected")
            assert resp.status_code == 403

    def test_wrong_api_key_returns_403(self):
        """Requests with wrong API key should return 403."""
        from schedflow.api.middleware import AuthMiddleware
        from schedflow.auth.security import AuthBackend, AuthResult

        class FixedKeyBackend(AuthBackend):
            def __init__(self, api_key: str = ""):
                self._api_key = api_key

            async def authenticate(self, request: Request):
                key = request.headers.get("X-API-Key", "")
                if key and key == self._api_key:
                    return AuthResult(success=True, user_id="test", method="apikey")
                return AuthResult(success=False)

        app = _make_app()
        backend = FixedKeyBackend(api_key="secret-token")
        app.add_middleware(AuthMiddleware, backends=[backend])

        with TestClient(app) as client:
            resp = client.get("/protected", headers={"X-API-Key": "wrong"})
            assert resp.status_code == 403

    def test_correct_api_key_passes(self):
        """Requests with correct API key should pass."""
        from schedflow.api.middleware import AuthMiddleware
        from schedflow.auth.security import AuthBackend, AuthResult

        class FixedKeyBackend(AuthBackend):
            def __init__(self, api_key: str = ""):
                self._api_key = api_key

            async def authenticate(self, request: Request):
                key = request.headers.get("X-API-Key", "")
                if key and key == self._api_key:
                    return AuthResult(success=True, user_id="test", method="apikey")
                return AuthResult(success=False)

        app = _make_app()
        backend = FixedKeyBackend(api_key="secret-token")
        app.add_middleware(AuthMiddleware, backends=[backend])

        with TestClient(app) as client:
            resp = client.get("/protected", headers={"X-API-Key": "secret-token"})
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}

    def test_no_auth_required_when_no_backend(self):
        """When no auth backend is configured, requests should pass through."""
        app = _make_app()
        with TestClient(app) as client:
            resp = client.get("/protected")
            assert resp.status_code == 200


class TestAuthBackendInterface:
    def test_auth_backend_is_abstract(self):
        """AuthBackend should be an abstract base class."""
        from schedflow.auth.security import AuthBackend

        with pytest.raises(TypeError):
            AuthBackend()

    def test_auth_backend_has_authenticate_method(self):
        """AuthBackend should define an authenticate abstract method."""
        from schedflow.auth.security import AuthBackend

        assert hasattr(AuthBackend, "authenticate")
        assert getattr(AuthBackend.authenticate, "__isabstractmethod__", False)


class TestQueryParamAuth:
    """SSE (EventSource) cannot send Authorization headers, so credentials
    must also be accepted via query parameters."""

    def _make_authed_app(self):
        from schedflow.api import create_app
        from schedflow.core import Scheduler

        return create_app(Scheduler())

    def _make_token(self, client):
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["token"]

    def test_jwt_via_token_query_param(self):
        """A valid JWT passed as ?token= should authenticate a request."""
        app = self._make_authed_app()
        with TestClient(app) as client:
            token = self._make_token(client)
            resp = client.get("/api/v1/settings/theme", params={"token": token})
            assert resp.status_code == 200

    def test_api_key_via_query_param(self):
        """A valid API key passed as ?api_key= should authenticate a request."""
        app = self._make_authed_app()
        with TestClient(app) as client:
            token = self._make_token(client)
            create_resp = client.post(
                "/api/v1/auth/apikeys",
                json={"name": "sse-key"},
                headers={"Authorization": f"Bearer {token}"},
            )
            plain_key = create_resp.json()["data"]["plain_key"]
            resp = client.get(
                "/api/v1/settings/theme", params={"api_key": plain_key}
            )
            assert resp.status_code == 200

    def test_missing_credentials_still_rejected(self):
        """Requests without any credentials must still be rejected."""
        app = self._make_authed_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/settings/theme")
            assert resp.status_code == 403


def test_token_bucket_limiter_rejects_after_capacity():
    from schedflow.api.middleware import TokenBucketLimiter

    limiter = TokenBucketLimiter({"enabled": True, "rpm": 1})

    assert limiter.allow("client")[0] is True
    allowed, retry_after = limiter.allow("client")
    assert allowed is False
    assert retry_after > 0


def test_rate_limit_middleware_returns_429_for_write_requests():
    from schedflow.api import create_app
    from schedflow.core import Scheduler
    from schedflow.settings.services import set_rate_limit_config

    set_rate_limit_config({"enabled": True, "rpm": 1})
    try:
        app = create_app(Scheduler(), include_auth=False)
        payload = {
            "workflow": {
                "flow_id": "rate",
                "nodes": [
                    {
                        "node_id": "a",
                        "task": {
                            "type": "python_callable",
                            "ref": "os:getcwd",
                        },
                    }
                ],
                "edges": [],
            },
            "job_id": "rate-job",
        }
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.post("/api/jobs", json=payload).status_code == 200
            blocked = client.post("/api/jobs", json=payload)
            assert blocked.status_code == 429
            assert "Retry-After" in blocked.headers
            assert client.get("/api/jobs").status_code == 200
    finally:
        set_rate_limit_config({"enabled": False, "rpm": 120})
