"""Tests for settings API endpoints (theme and variables).

These tests verify the settings management system:
- Theme: GET/PUT with validation and persistence
- Variables: CRUD with duplicate name handling

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
    (users, api_keys, system_settings, variables, etc.) is created before
    any test runs.
    """
    app = create_app(Scheduler())
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestTheme:
    """Verify the theme GET/PUT endpoints, validation, and persistence."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, client):
        """Ensure an admin user exists and store a valid JWT token for
        each test method."""
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, (
            f"init-setup failed: {resp.status_code} {resp.json()}"
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        self.token = resp.json()["data"]["token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_default_theme(self, client):
        """The default theme should be 'light'."""
        resp = client.get(
            "/api/v1/settings/theme",
            headers=self._headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["theme"] == "light"

    def test_set_theme(self, client):
        """PUT /api/v1/settings/theme should update the theme."""
        client.put(
            "/api/v1/settings/theme",
            json={"theme": "dark"},
            headers=self._headers(),
        )
        resp = client.get(
            "/api/v1/settings/theme",
            headers=self._headers(),
        )
        assert resp.json()["data"]["theme"] == "dark"

    def test_invalid_theme_rejected(self, client):
        """A theme value other than 'light' or 'dark' should be rejected."""
        resp = client.put(
            "/api/v1/settings/theme",
            json={"theme": "blue"},
            headers=self._headers(),
        )
        assert resp.status_code == 422

    def test_theme_persists(self, client):
        """The theme setting should persist across consecutive requests."""
        client.put(
            "/api/v1/settings/theme",
            json={"theme": "dark"},
            headers=self._headers(),
        )
        resp = client.get(
            "/api/v1/settings/theme",
            headers=self._headers(),
        )
        assert resp.json()["data"]["theme"] == "dark"


class TestVariables:
    """Verify variables CRUD endpoints and duplicate name handling."""

    @pytest.fixture(autouse=True)
    def setup_auth(self, client):
        """Ensure an admin user exists and store a valid JWT token for
        each test method."""
        resp = client.post(
            "/api/v1/auth/init-setup",
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, (
            f"init-setup failed: {resp.status_code} {resp.json()}"
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        self.token = resp.json()["data"]["token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_create_variable(self, client):
        """POST /api/v1/settings/variables should create a new variable."""
        resp = client.post(
            "/api/v1/settings/variables",
            json={"name": "DEFAULT_TIMEOUT", "value": "30"},
            headers=self._headers(),
        )
        assert resp.status_code == 200, (
            f"create failed: {resp.status_code} {resp.json()}"
        )
        data = resp.json()["data"]
        assert data["name"] == "DEFAULT_TIMEOUT"
        assert data["value"] == "30"
        assert data["id"]

    def test_list_variables(self, client):
        """GET /api/v1/settings/variables should return all created variables."""
        client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR1", "value": "a"},
            headers=self._headers(),
        )
        client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR2", "value": "b"},
            headers=self._headers(),
        )
        resp = client.get(
            "/api/v1/settings/variables",
            headers=self._headers(),
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_update_variable(self, client):
        """PUT /api/v1/settings/variables/{id} should update the variable."""
        create_resp = client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR1", "value": "old"},
            headers=self._headers(),
        )
        var_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/v1/settings/variables/{var_id}",
            json={"value": "new"},
            headers=self._headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == "new"

    def test_delete_variable(self, client):
        """DELETE /api/v1/settings/variables/{id} should remove the variable."""
        create_resp = client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR1", "value": "x"},
            headers=self._headers(),
        )
        var_id = create_resp.json()["data"]["id"]

        client.delete(
            f"/api/v1/settings/variables/{var_id}",
            headers=self._headers(),
        )
        resp = client.get(
            "/api/v1/settings/variables",
            headers=self._headers(),
        )
        assert len(resp.json()["data"]) == 0

    def test_duplicate_name_rejected(self, client):
        """Creating a variable with a duplicate name should return 409."""
        client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR1", "value": "a"},
            headers=self._headers(),
        )
        resp = client.post(
            "/api/v1/settings/variables",
            json={"name": "VAR1", "value": "b"},
            headers=self._headers(),
        )
        assert resp.status_code == 409, (
            f"Expected 409 for duplicate name, got {resp.status_code}: {resp.json()}"
        )
