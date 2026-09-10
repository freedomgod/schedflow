import sqlite3
import uuid

from fastapi import APIRouter, HTTPException, Request

from schedflow.api.schemas import (
    APIResponse,
    RateLimitRequest,
    ThemeRequest,
    ThemeResponse,
    VariableCreateRequest,
    VariableItem,
    VariableUpdateRequest,
    WebhooksRequest,
)
from schedflow.settings.models import (
    create_variable,
    delete_variable,
    list_variables,
    update_variable,
)
from schedflow.settings.services import (
    get_rate_limit_config,
    get_theme,
    get_webhooks_config,
    set_rate_limit_config,
    set_theme,
    set_webhooks_config,
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


# ── Webhooks ──────────────────────────────────────────

@router.get("/webhooks")
def webhooks_get():
    return APIResponse(data=get_webhooks_config())


@router.put("/webhooks")
def webhooks_set(request_body: WebhooksRequest, request: Request):
    configs = [
        item.model_dump(exclude_none=True)
        for item in request_body.webhooks
    ]
    set_webhooks_config(configs)
    _apply_webhook_sink(request, configs)
    return APIResponse(data=configs)


def _apply_webhook_sink(request: Request, configs: list[dict]) -> None:
    from schedflow.core.webhook import WebhookEventSink

    state = request.app.state
    scheduler = getattr(state, "scheduler_api", None) or getattr(
        state, "scheduler", None
    )
    sink = getattr(state, "webhook_sink", None)
    if sink is None and configs and scheduler is not None:
        sink = WebhookEventSink(configs)
        sink.start(scheduler)
        state.webhook_sink = sink
        return
    if sink is None:
        return
    if configs:
        sink.reload(configs)
    else:
        sink.close()
        state.webhook_sink = None


# ── Rate limit ────────────────────────────────────────

@router.get("/rate-limit")
def rate_limit_get():
    return APIResponse(data=get_rate_limit_config())


@router.put("/rate-limit")
def rate_limit_set(request_body: RateLimitRequest, request: Request):
    config = request_body.model_dump()
    set_rate_limit_config(config)
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None:
        limiter.reload(config)
    return APIResponse(data=get_rate_limit_config())
