"""Tests for auth init, login, and API key flows.

These tests verify the complete authentication system:
- Init flow: checking need_init status, creating the first admin user
- Login flow: JWT-based authentication with token verification
- API key flow: create, list, update, delete, and authenticate with API keys

The ``isolated_meta_db`` autouse fixture in ``conftest.py`` redirects the
metadata database to a temporary file for every test, so tests never touch
the real runtime database.
"""
import pytest
from fastapi.testclient import TestClient

from schedflow.api import create_app
from schedflow.core import Scheduler


@pytest.fixture
def client():
    """Yield a TestClient connected to a fresh application instance.

    The ``with`` block triggers the FastAPI lifespan, which starts the
    background scheduler and ensures the metadata database schema
    (users, api_keys, etc.) is created before any test runs.
    """
    app = create_app(Scheduler())
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestInitFlow:
    """Verify the initial-setup flow: checking status, creating the first
    admin user, and ensuring subsequent init attempts are rejected."""

    def test_init_status_returns_need_init(self, client):
        """A freshly created database should report need_init=True."""
        resp = client.get("/api/v1/auth/init-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["need_init"] is True

    def test_init_setup_creates_admin(self, client):
        """POST /api/v1/auth/init-setup should create the admin user and
        return a JWT token."""
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["token"]
        assert data["data"]["username"] == "admin"

    def test_init_setup_rejects_duplicate(self, client):
        """A second init-setup call should be rejected with 409."""
        # Create the initial admin
        client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        # Attempt to initialize again
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin2", "password": "admin123"},
        )
        assert resp.status_code == 409

    def test_init_status_after_setup(self, client):
        """After admin creation, need_init should report False."""
        client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        resp = client.get("/api/v1/auth/init-status")
        assert resp.json()["data"]["need_init"] is False


class TestLoginFlow:
    """Verify JWT-based login and protected-endpoint access."""

    @pytest.fixture(autouse=True)
    def setup_admin(self, client):
        """Ensure an admin user exists and store a valid JWT token for
        each test method."""
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, (
            f"init-setup failed: {resp.status_code} {resp.json()}"
        )
        self.token = resp.json()["data"]["token"]

    def test_login_success(self, client):
        """POST /api/v1/auth/login with valid credentials returns a token."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["token"]

    def test_login_wrong_password(self, client):
        """POST /api/v1/auth/login with wrong password returns 401."""
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_protected_endpoint_without_token(self, client):
        """Accessing a protected endpoint without credentials returns 403."""
        resp = client.get("/api/jobs")
        assert resp.status_code == 403

    def test_protected_endpoint_with_token(self, client):
        """A valid Bearer token should grant access to protected endpoints."""
        resp = client.get(
            "/api/jobs",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert resp.status_code == 200

    def test_protected_endpoint_with_invalid_token(self, client):
        """An invalid Bearer token should be rejected with 403."""
        resp = client.get(
            "/api/jobs",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 403


class TestApiKeyFlow:
    """Verify API key CRUD and key-based authentication."""

    @pytest.fixture(autouse=True)
    def setup_admin(self, client):
        """Ensure an admin user exists and store a JWT token for each test
        method."""
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, (
            f"init-setup failed: {resp.status_code} {resp.json()}"
        )
        self.token = resp.json()["data"]["token"]

    def _auth_header(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_create_api_key(self, client):
        """POST /api/v1/auth/apikeys should create a new API key."""
        resp = client.post(
            "/api/v1/auth/apikeys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "test-key"
        assert data["plain_key"].startswith("ak_")

    def test_list_api_keys(self, client):
        """GET /api/v1/auth/apikeys should return existing keys without
        exposing the plain key value."""
        client.post(
            "/api/v1/auth/apikeys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        resp = client.get("/api/v1/auth/apikeys", headers=self._auth_header())
        assert resp.status_code == 200
        keys = resp.json()["data"]
        assert len(keys) == 1
        assert "plain_key" not in keys[0]  # Full key never returned in list

    def test_api_key_auth(self, client):
        """An API key should be usable for authentication via X-API-Key."""
        # Create API key
        create_resp = client.post(
            "/api/v1/auth/apikeys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        plain_key = create_resp.json()["data"]["plain_key"]

        # Use API key to access a protected endpoint
        resp = client.get("/api/jobs", headers={"X-API-Key": plain_key})
        assert resp.status_code == 200

    def test_invalid_api_key_rejected(self, client):
        """An invalid API key should be rejected with 403."""
        resp = client.get(
            "/api/jobs", headers={"X-API-Key": "ak_invalid"}
        )
        assert resp.status_code == 403

    def test_disable_api_key(self, client):
        """A disabled API key should no longer authenticate successfully."""
        create_resp = client.post(
            "/api/v1/auth/apikeys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        key_id = create_resp.json()["data"]["id"]
        plain_key = create_resp.json()["data"]["plain_key"]

        # Disable the key
        client.put(
            f"/api/v1/auth/apikeys/{key_id}",
            json={"is_active": False},
            headers=self._auth_header(),
        )

        # Now this key should be rejected
        resp = client.get("/api/v1/jobs", headers={"X-API-Key": plain_key})
        assert resp.status_code == 403

    def test_delete_api_key(self, client):
        """A deleted API key should disappear from the key listing."""
        create_resp = client.post(
            "/api/v1/auth/apikeys",
            json={"name": "test-key"},
            headers=self._auth_header(),
        )
        key_id = create_resp.json()["data"]["id"]

        client.delete(
            f"/api/v1/auth/apikeys/{key_id}",
            headers=self._auth_header(),
        )

        resp = client.get(
            "/api/v1/auth/apikeys", headers=self._auth_header()
        )
        assert len(resp.json()["data"]) == 0
