import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone

from schedflow.configs.settings import settings

# Kept for backwards compatibility; actual connections are handled by
# ``configs.config._get_conn`` which uses the project-root-resolved path.
META_DB = str(settings.meta_db_path)


def _get_conn() -> sqlite3.Connection:
    from schedflow.configs.config import _get_conn as _core_get_conn
    return _core_get_conn()


# ── User ──────────────────────────────────────────────

def create_user(user_id: str, username: str, password_hash: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, username, password_hash),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_users() -> int:
    conn = _get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


# ── API Key ───────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (plain_key, key_hash, key_prefix)."""
    plain = "ak_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(plain.encode()).hexdigest()
    key_prefix = plain[:11]  # "ak_" + first 8 hex chars
    return plain, key_hash, key_prefix


def create_api_key(key_id: str, name: str, key_hash: str, key_prefix: str) -> None:
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO api_keys (id, name, key_hash, key_prefix, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key_id, name, key_hash, key_prefix, now),
        )
        conn.commit()
    finally:
        conn.close()


def list_api_keys() -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, key_prefix, is_active, last_used_at, created_at, expires_at "
            "FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_api_key_by_hash(key_hash: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_api_key(key_id: str, **fields) -> None:
    allowed = {"name", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [key_id]
    conn = _get_conn()
    try:
        conn.execute(f"UPDATE api_keys SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def update_api_key_last_used(key_id: str) -> None:
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, key_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_api_key(key_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
    finally:
        conn.close()
