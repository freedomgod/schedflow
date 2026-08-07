import hashlib
import secrets
import time
import uuid

import jwt
import bcrypt

from schedflow.auth.models import (
    count_users,
    create_user,
    get_user_by_username,
    get_api_key_by_hash,
    update_api_key_last_used,
)
from schedflow.configs.config import _get_conn

SECRET_KEY_CACHE: str | None = None


def _get_secret_key() -> str:
    global SECRET_KEY_CACHE
    if SECRET_KEY_CACHE:
        return SECRET_KEY_CACHE

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = 'secret_key'"
        ).fetchone()
        if row:
            SECRET_KEY_CACHE = row[0]
            return SECRET_KEY_CACHE

        new_key = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO system_settings (key, value) VALUES ('secret_key', ?)",
            (new_key,),
        )
        conn.commit()
        SECRET_KEY_CACHE = new_key
        return new_key
    finally:
        conn.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_jwt_token(user_id: str) -> str:
    secret = _get_secret_key()
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + 86400}  # 24h
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_jwt_token(token: str) -> dict | None:
    try:
        secret = _get_secret_key()
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None


def needs_init() -> bool:
    return count_users() == 0


def setup_admin(username: str, password: str) -> dict:
    if not needs_init():
        raise ValueError("System already initialized")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    user_id = uuid.uuid4().hex
    password_hash = hash_password(password)
    create_user(user_id, username, password_hash)
    token = create_jwt_token(user_id)
    return {"user_id": user_id, "username": username, "token": token}


def login(username: str, password: str) -> dict:
    user = get_user_by_username(username)
    if not user:
        raise ValueError("Invalid username or password")
    if not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid username or password")

    token = create_jwt_token(user["id"])
    return {"user_id": user["id"], "username": user["username"], "token": token}


def verify_api_key(plain_key: str) -> dict | None:
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    key_record = get_api_key_by_hash(key_hash)
    if not key_record:
        return None
    if not key_record["is_active"]:
        return None
    if key_record["expires_at"]:
        from datetime import datetime, timezone
        expires = datetime.fromisoformat(key_record["expires_at"])
        if expires < datetime.now(timezone.utc):
            return None
    update_api_key_last_used(key_record["id"])
    return key_record
