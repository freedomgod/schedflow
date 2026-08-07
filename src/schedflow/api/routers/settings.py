import sqlite3
import uuid

from fastapi import APIRouter, HTTPException

from schedflow.api.schemas import (
    APIResponse,
    ThemeRequest,
    ThemeResponse,
    VariableCreateRequest,
    VariableUpdateRequest,
    VariableItem,
)
from schedflow.settings.services import get_theme, set_theme
from schedflow.settings.models import (
    list_variables,
    create_variable,
    update_variable,
    delete_variable,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Theme ─────────────────────────────────────────────

@router.get("/theme")
def theme_get():
    return APIResponse(data=ThemeResponse(theme=get_theme()).model_dump())


@router.put("/theme")
def theme_set(request: ThemeRequest):
    set_theme(request.theme)
    return APIResponse(message="Theme updated")


# ── Variables ─────────────────────────────────────────

@router.get("/variables")
def variables_list():
    items = list_variables()
    return APIResponse(data=[
        VariableItem(
            id=v["id"],
            name=v["name"],
            value=v["value"],
            description=v.get("description"),
            created_at=v["created_at"],
            updated_at=v["updated_at"],
        ).model_dump() for v in items
    ])


@router.post("/variables")
def variables_create(request: VariableCreateRequest):
    var_id = uuid.uuid4().hex
    try:
        result = create_variable(var_id, request.name, request.value, request.description)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Variable name already exists")
    return APIResponse(data=VariableItem(
        id=result["id"], name=result["name"], value=result["value"],
        description=result.get("description"),
        created_at=result["created_at"], updated_at=result["updated_at"],
    ).model_dump())


@router.put("/variables/{var_id}")
def variables_update(var_id: str, request: VariableUpdateRequest):
    result = update_variable(var_id, **request.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Variable not found")
    return APIResponse(data=VariableItem(
        id=result["id"], name=result["name"], value=result["value"],
        description=result.get("description"),
        created_at=result["created_at"], updated_at=result["updated_at"],
    ).model_dump())


@router.delete("/variables/{var_id}")
def variables_delete(var_id: str):
    delete_variable(var_id)
    return APIResponse(message="Variable deleted")
