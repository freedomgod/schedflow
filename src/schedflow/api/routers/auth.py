import uuid

from fastapi import APIRouter

from schedflow.api.schemas import (
    APIResponse,
    LoginRequest,
    InitSetupRequest,
    InitStatusResponse,
    AuthResponse,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyItem,
    ApiKeyUpdateRequest,
)
from schedflow.auth.services import needs_init, setup_admin, login
from schedflow.auth.models import (
    generate_api_key,
    create_api_key,
    list_api_keys,
    update_api_key,
    delete_api_key,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/init-status")
def get_init_status():
    return APIResponse(data=InitStatusResponse(need_init=needs_init()).model_dump())


@router.post("/init-setup")
def init_setup(request: InitSetupRequest):
    if not needs_init():
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="System already initialized")
    result = setup_admin(request.username, request.password)
    return APIResponse(data=AuthResponse(**result).model_dump())


@router.post("/login")
def user_login(request: LoginRequest):
    try:
        result = login(request.username, request.password)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail=str(e))
    return APIResponse(data=AuthResponse(**result).model_dump())


# ── API Keys ──────────────────────────────────────────

@router.get("/apikeys")
def get_apikeys():
    keys = list_api_keys()
    return APIResponse(data=[
        ApiKeyItem(
            id=k["id"],
            name=k["name"],
            key_prefix=k["key_prefix"],
            is_active=bool(k["is_active"]),
            last_used_at=k.get("last_used_at"),
            created_at=k["created_at"],
            expires_at=k.get("expires_at"),
        ).model_dump() for k in keys
    ])


@router.post("/apikeys")
def create_apikey(request: ApiKeyCreateRequest):
    plain_key, key_hash, key_prefix = generate_api_key()
    key_id = uuid.uuid4().hex
    create_api_key(key_id, request.name, key_hash, key_prefix)

    from schedflow.auth.models import _get_conn
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT created_at FROM api_keys WHERE id = ?", (key_id,)
        ).fetchone()
        created_at = row[0] if row else ""
    finally:
        conn.close()

    return APIResponse(data=ApiKeyCreateResponse(
        id=key_id, name=request.name, key_prefix=key_prefix,
        plain_key=plain_key, created_at=created_at,
    ).model_dump())


@router.put("/apikeys/{key_id}")
def update_apikey(key_id: str, request: ApiKeyUpdateRequest):
    fields = request.model_dump(exclude_none=True)
    update_api_key(key_id, **fields)
    return APIResponse(message="API key updated")


@router.delete("/apikeys/{key_id}")
def delete_apikey(key_id: str):
    delete_api_key(key_id)
    return APIResponse(message="API key deleted")
