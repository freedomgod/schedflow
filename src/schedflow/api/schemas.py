"""API request and response schemas.

Pydantic models for API request validation and response serialization,
covering jobstore/executor configuration, authentication, API key
management, and user settings. Job CRUD schemas live in
``schedflow.api.rest.schemas``.

Models:
    APIResponse — Standardized API response wrapper with code/data/message.
    RescheduleRequest — Trigger update for an existing job.
    LoginRequest / InitSetupRequest / AuthResponse / InitStatusResponse —
        Authentication and user initialization models.
    ApiKeyCreateRequest / ApiKeyCreateResponse / ApiKeyItem /
        ApiKeyUpdateRequest — API key management models.
    ThemeRequest / ThemeResponse / VariableCreateRequest /
        VariableUpdateRequest / VariableItem — User settings models.
    JobstoreConfigureRequest / ExecutorConfigureRequest /
        JobstoreUpdateResponse / ExecutorUpdateResponse /
        JobstoreMigrateResponse — Jobstore and executor configuration models.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator


class APIResponse(BaseModel):
    code: int = 0
    data: Optional[Any] = None
    message: str = "ok"


class RescheduleRequest(BaseModel):
    trigger: str
    trigger_args: Optional[Dict[str, Any]] = None


class JobstoreConfigureRequest(BaseModel):
    type: str
    config: Dict[str, Any] = {}


class ExecutorConfigureRequest(BaseModel):
    type: str
    config: Dict[str, Any] = {}


class ExecutorUpdateResponse(BaseModel):
    alias: str
    plugin_type: str
    config: Dict[str, Any]
    type_changed: bool
    message: str


class JobstoreUpdateResponse(BaseModel):
    alias: str
    plugin_type: str
    config: Dict[str, Any]
    needs_migration: bool
    affected_jobs_count: int
    old_plugin_type: str
    message: str


class JobstoreMigrateResponse(BaseModel):
    alias: str
    migrated_count: int
    message: str
    error: Optional[str] = None


# ── Auth ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class InitSetupRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class AuthResponse(BaseModel):
    user_id: str
    username: str
    token: str


class InitStatusResponse(BaseModel):
    need_init: bool


# ── API Key ──────────────────────────────────────────

class ApiKeyCreateRequest(BaseModel):
    name: str


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    plain_key: str
    created_at: str


class ApiKeyItem(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: str
    expires_at: Optional[str] = None


class ApiKeyUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


# ── Settings ─────────────────────────────────────────

class ThemeRequest(BaseModel):
    theme: str

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v):
        if v not in ("light", "dark"):
            raise ValueError("theme must be 'light' or 'dark'")
        return v


class ThemeResponse(BaseModel):
    theme: str


class VariableCreateRequest(BaseModel):
    name: str
    value: str
    description: Optional[str] = None


class VariableUpdateRequest(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None


class VariableItem(BaseModel):
    id: str
    name: str
    value: str
    description: Optional[str] = None
    created_at: str
    updated_at: str
