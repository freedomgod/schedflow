"""Scheduler metadata persistence.

Stores scheduler-level configuration (jobstore definitions) in a SQLite
metadata database so that dynamically added jobstores survive restarts.

The metadata database is separate from individual jobstore databases and
serves as the bootstrap source for scheduler configuration on startup.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from schedflow.configs.settings import settings

# Resolved against the project root (not the CWD), so the same database is
# used regardless of where the process is launched from.
DEFAULT_META_DB = settings.meta_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobstore_config (
    alias       TEXT PRIMARY KEY,
    plugin_type TEXT    NOT NULL,
    config_json TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS executor_config (
    alias       TEXT PRIMARY KEY,
    plugin_type TEXT    NOT NULL,
    config_json TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    key_hash     TEXT UNIQUE NOT NULL,
    key_prefix   TEXT NOT NULL,
    is_active    INTEGER DEFAULT 1,
    last_used_at TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    expires_at   TEXT
);
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS variables (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    value       TEXT NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""


def _get_conn() -> sqlite3.Connection:
    db_path = str(DEFAULT_META_DB)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _ensure_default_component_configs(conn)
    return conn


def _ensure_default_component_configs(conn: sqlite3.Connection) -> None:
    """Persist the built-in default jobstore/executor when missing (idempotent).

    Keeps any existing row (including a user-modified ``default`` config), so
    this only seeds the initial values on first initialization.
    """
    if (
        conn.execute(
            "SELECT 1 FROM jobstore_config WHERE alias = 'default'"
        ).fetchone()
        is None
    ):
        conn.execute(
            "INSERT INTO jobstore_config (alias, plugin_type, config_json) "
            "VALUES ('default', 'memory', '{}')"
        )
    if (
        conn.execute(
            "SELECT 1 FROM executor_config WHERE alias = 'default'"
        ).fetchone()
        is None
    ):
        conn.execute(
            "INSERT INTO executor_config (alias, plugin_type, config_json) "
            "VALUES ('default', 'threadpool', '{\"max_workers\": 10}')"
        )
    conn.commit()


def restore_component_configs(scheduler) -> None:
    """Re-apply persisted jobstore/executor configs onto a scheduler.

    For an alias that already exists (e.g. the built-in ``default``), the
    persisted config replaces the in-memory instance so that edits to the
    default components survive restarts.
    """
    from schedflow.core.plugins import EXECUTOR_PLUGINS, JOBSTORE_PLUGINS

    for alias, cfg in load_jobstore_configs().items():
        plugin_type = cfg.pop("type")
        try:
            if alias in scheduler._jobstores:
                scheduler.set_jobstore(
                    scheduler._resolve_plugin(
                        plugin_type, cfg, JOBSTORE_PLUGINS, "jobstore"
                    ),
                    alias,
                )
            else:
                scheduler.add_jobstore(plugin_type, alias, **cfg)
        except (ValueError, KeyError):
            pass  # plugin unavailable — keep the existing store
    for alias, cfg in load_executor_configs().items():
        plugin_type = cfg.pop("type")
        try:
            if alias in scheduler._executors:
                scheduler.set_executor(
                    scheduler._resolve_plugin(
                        plugin_type, cfg, EXECUTOR_PLUGINS, "executor"
                    ),
                    alias,
                )
            else:
                scheduler.add_executor(plugin_type, alias, **cfg)
        except (ValueError, KeyError):
            pass


def load_jobstore_configs() -> dict[str, dict[str, Any]]:
    """Load persisted jobstore configurations from the metadata database.

    Returns a dict mapping alias -> config where each config contains
    ``type`` (the plugin name) plus the keyword arguments suitable for
    ``scheduler.add_jobstore()``.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT alias, plugin_type, config_json FROM jobstore_config"
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, dict[str, Any]] = {}
    for alias, plugin_type, config_json in rows:
        cfg = json.loads(config_json)
        cfg["type"] = plugin_type
        result[alias] = cfg
    return result


def get_jobstore_config(alias: str) -> dict[str, Any] | None:
    """Get persisted configuration for a single jobstore by alias.

    Returns a dict containing ``type`` and keyword arguments, or None
    if the alias is not found.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT plugin_type, config_json FROM jobstore_config WHERE alias = ?",
            (alias,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    plugin_type, config_json = row
    cfg = json.loads(config_json)
    cfg["type"] = plugin_type
    return cfg


def save_jobstore_config(alias: str, plugin_type: str, config: dict[str, Any]) -> None:
    """Persist a jobstore configuration to the metadata database."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO jobstore_config (alias, plugin_type, config_json) "
            "VALUES (?, ?, ?)",
            (alias, plugin_type, json.dumps(config, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def update_jobstore_config(alias: str, plugin_type: str, config: dict[str, Any]) -> None:
    """Update an existing jobstore config in the meta database."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT alias FROM jobstore_config WHERE alias = ?", (alias,)
        )
        if cur.fetchone() is None:
            raise KeyError(f"No such jobstore config: {alias}")
        conn.execute(
            "UPDATE jobstore_config SET plugin_type = ?, config_json = ? WHERE alias = ?",
            (plugin_type, json.dumps(config, ensure_ascii=False), alias),
        )
        conn.commit()
    finally:
        conn.close()


def remove_jobstore_config(alias: str) -> None:
    """Remove a jobstore configuration from the metadata database."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM jobstore_config WHERE alias = ?", (alias,))
        conn.commit()
    finally:
        conn.close()


def load_executor_configs() -> dict[str, dict[str, Any]]:
    """Load persisted executor configurations from the metadata database."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT alias, plugin_type, config_json FROM executor_config"
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, dict[str, Any]] = {}
    for alias, plugin_type, config_json in rows:
        cfg = json.loads(config_json)
        cfg["type"] = plugin_type
        result[alias] = cfg
    return result


def get_executor_config(alias: str) -> dict[str, Any] | None:
    """Get persisted configuration for a single executor by alias."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT plugin_type, config_json FROM executor_config WHERE alias = ?",
            (alias,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    plugin_type, config_json = row
    cfg = json.loads(config_json)
    cfg["type"] = plugin_type
    return cfg


def save_executor_config(alias: str, plugin_type: str, config: dict[str, Any]) -> None:
    """Persist an executor configuration to the metadata database."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO executor_config (alias, plugin_type, config_json) "
            "VALUES (?, ?, ?)",
            (alias, plugin_type, json.dumps(config, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def update_executor_config(alias: str, plugin_type: str, config: dict[str, Any]) -> None:
    """Update an existing executor config in the meta database."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT alias FROM executor_config WHERE alias = ?", (alias,)
        )
        if cur.fetchone() is None:
            raise KeyError(f"No such executor config: {alias}")
        conn.execute(
            "UPDATE executor_config SET plugin_type = ?, config_json = ? WHERE alias = ?",
            (plugin_type, json.dumps(config, ensure_ascii=False), alias),
        )
        conn.commit()
    finally:
        conn.close()


def remove_executor_config(alias: str) -> None:
    """Remove an executor configuration from the metadata database."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM executor_config WHERE alias = ?", (alias,))
        conn.commit()
    finally:
        conn.close()
