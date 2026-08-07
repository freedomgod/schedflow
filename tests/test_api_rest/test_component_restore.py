"""Lifespan restores persisted component configs into the core scheduler."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import schedflow.configs.config as config_module
from schedflow.api.rest import create_app
from schedflow.configs.config import (
    remove_executor_config,
    remove_jobstore_config,
    save_executor_config,
    save_jobstore_config,
)
from schedflow.core import Scheduler
from schedflow.core.scheduler import STATE_RUNNING


@pytest.fixture
def temp_meta_db(monkeypatch):
    """Redirect the metadata DB to a temporary file for isolated testing."""
    fd, tmp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    tmp_path = Path(tmp_name)
    monkeypatch.setattr(config_module, "DEFAULT_META_DB", tmp_path)
    yield tmp_path
    if tmp_path.exists():
        tmp_path.unlink()


def test_lifespan_restores_persisted_components(temp_meta_db) -> None:
    save_executor_config("fast", "threadpool", {"max_workers": 4})
    save_jobstore_config("secondary", "memory", {})
    scheduler = Scheduler()
    app = create_app(scheduler, title="component-restore")
    try:
        with TestClient(app):
            assert app.state.scheduler_api.get_executor("fast") is not None
            assert app.state.scheduler_api.get_jobstore("secondary") is not None
            assert app.state.scheduler_api.state == STATE_RUNNING
    finally:
        remove_executor_config("fast")
        remove_jobstore_config("secondary")
