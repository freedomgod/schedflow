import json
from datetime import datetime, timezone
from schedflow.configs.config import _get_conn


# ── System Settings ───────────────────────────────────

def get_setting(key: str) -> str | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) "
            "VALUES (?, ?, ?)",
            (key, value, now),
        )
        conn.commit()
    finally:
        conn.close()


# ── Variables ─────────────────────────────────────────

def list_variables() -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, value, description, created_at, updated_at "
            "FROM variables ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_variable(var_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, name, value, description, created_at, updated_at "
            "FROM variables WHERE id = ?", (var_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_variable(var_id: str, name: str, value: str, description: str | None) -> dict:
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO variables (id, name, value, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (var_id, name, value, description, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_variable(var_id)


def update_variable(var_id: str, **fields) -> dict | None:
    allowed = {"name", "value", "description"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_variable(var_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [var_id]
    conn = _get_conn()
    try:
        conn.execute(f"UPDATE variables SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()
    return get_variable(var_id)


def delete_variable(var_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM variables WHERE id = ?", (var_id,))
        conn.commit()
    finally:
        conn.close()
