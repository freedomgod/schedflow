"""Tests for the scheduler metadata persistence module (configs/config.py)."""

import json
import os
import tempfile
from pathlib import Path

import pytest

import schedflow.configs.config as config_module
from schedflow.configs.config import (
    get_jobstore_config,
    load_executor_configs,
    load_jobstore_configs,
    save_jobstore_config,
    remove_jobstore_config,
    DEFAULT_META_DB,
)


@pytest.fixture
def temp_meta_db(monkeypatch):
    """Redirect the metadata DB to a temporary file for isolated testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    monkeypatch.setattr(config_module, "DEFAULT_META_DB", tmp_path)
    yield tmp_path
    # Cleanup
    if tmp_path.exists():
        tmp_path.unlink()


class TestSaveAndLoadConfig:
    def test_save_and_load_single(self, temp_meta_db):
        save_jobstore_config("default", "sqlalchemy", {"url": "sqlite:///test.db"})
        configs = load_jobstore_configs()
        assert "default" in configs
        assert configs["default"]["type"] == "sqlalchemy"
        assert configs["default"]["url"] == "sqlite:///test.db"

    def test_save_and_load_multiple(self, temp_meta_db):
        save_jobstore_config("store1", "memory", {})
        save_jobstore_config("store2", "redis", {"host": "localhost", "port": 6379})
        save_jobstore_config("store3", "mongodb", {"database": "testdb"})
        configs = load_jobstore_configs()
        assert len(configs) == 4  # 3 custom stores + persisted default
        assert configs["store1"]["type"] == "memory"
        assert configs["store2"]["type"] == "redis"
        assert configs["store2"]["host"] == "localhost"
        assert configs["store3"]["type"] == "mongodb"

    def test_replace_existing_config(self, temp_meta_db):
        save_jobstore_config("default", "memory", {})
        save_jobstore_config("default", "sqlalchemy", {"url": "sqlite:///new.db"})
        configs = load_jobstore_configs()
        assert len(configs) == 1
        assert configs["default"]["type"] == "sqlalchemy"
        assert configs["default"]["url"] == "sqlite:///new.db"

    def test_load_empty_db(self, temp_meta_db):
        """A fresh DB always contains the persisted built-in default jobstore."""
        configs = load_jobstore_configs()
        assert configs == {"default": {"type": "memory"}}

    def test_get_single_config(self, temp_meta_db):
        save_jobstore_config("default", "sqlalchemy", {"url": "sqlite:///test.db"})
    
        cfg = get_jobstore_config("default")
        assert cfg is not None
        assert cfg["type"] == "sqlalchemy"
        assert cfg["url"] == "sqlite:///test.db"

    def test_get_nonexistent_config(self, temp_meta_db):
    
        cfg = get_jobstore_config("nonexistent")
        assert cfg is None


class TestRemoveConfig:
    def test_remove_existing_config(self, temp_meta_db):
        save_jobstore_config("toremove", "memory", {})
        remove_jobstore_config("toremove")
        configs = load_jobstore_configs()
        assert "toremove" not in configs

    def test_remove_nonexistent_config(self, temp_meta_db):
        # Should not raise
        remove_jobstore_config("nonexistent")

    def test_remove_one_keeps_others(self, temp_meta_db):
        save_jobstore_config("store1", "memory", {})
        save_jobstore_config("store2", "memory", {})
        remove_jobstore_config("store1")
        configs = load_jobstore_configs()
        assert "store1" not in configs
        assert "store2" in configs


class TestDefaultMetaDB:
    def test_default_meta_db_is_path(self):
        assert isinstance(DEFAULT_META_DB, Path)

    def test_env_var_override(self, monkeypatch):
        from schedflow.configs import settings as settings_module
        import importlib
        monkeypatch.setattr(settings_module.settings, "SCHEDFLOW_META_DB", "custom_meta.db")
        importlib.reload(config_module)
        try:
            # Relative values are resolved against the project root
            assert config_module.DEFAULT_META_DB == settings_module.PROJECT_ROOT / "custom_meta.db"
        finally:
            # IMPORTANT: Restore the original value BEFORE reloading, otherwise
            # the reload picks up the monkeypatched value and permanently
            # corrupts the module-level DEFAULT_META_DB for all later tests.
            monkeypatch.undo()
            importlib.reload(config_module)


class TestDefaultComponentPersistence:
    def test_defaults_persisted_on_init(self, temp_meta_db):
        """The built-in default jobstore/executor are persisted automatically."""
        jobstores = load_jobstore_configs()
        executors = load_executor_configs()
        assert jobstores.get("default", {}).get("type") == "memory"
        assert executors.get("default", {}).get("type") == "threadpool"
        assert executors.get("default", {}).get("max_workers") == 10

    def test_defaults_idempotent(self, temp_meta_db):
        """Re-opening the DB does not duplicate or overwrite default rows."""
        config_module._get_conn().close()
        config_module._get_conn().close()
        assert len(load_jobstore_configs()) == 1
        assert len(load_executor_configs()) == 1

    def test_existing_default_config_not_overwritten(self, temp_meta_db):
        """A user-modified default config survives further DB access."""
        save_jobstore_config("default", "sqlalchemy", {"url": "sqlite:///custom.db"})
        config_module._get_conn().close()
        cfg = load_jobstore_configs()["default"]
        assert cfg["type"] == "sqlalchemy"
        assert cfg["url"] == "sqlite:///custom.db"
