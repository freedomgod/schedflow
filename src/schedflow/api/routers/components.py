from fastapi import APIRouter, Depends, HTTPException

from schedflow.configs.config import (
    get_jobstore_config, load_jobstore_configs, save_jobstore_config, remove_jobstore_config,
    update_jobstore_config,
    load_executor_configs, save_executor_config, remove_executor_config,
    update_executor_config,
)
from schedflow.core.plugins import EXECUTOR_PLUGINS, JOBSTORE_PLUGINS
from schedflow.core.scheduler import Scheduler
from schedflow.api.deps import get_core_scheduler
from schedflow.api.schemas import APIResponse, JobstoreConfigureRequest, ExecutorConfigureRequest, RescheduleRequest, ExecutorUpdateResponse, JobstoreUpdateResponse, JobstoreMigrateResponse
from schedflow.triggers.base import Trigger
from schedflow.triggers.registry import TRIGGER_PLUGINS

router = APIRouter(prefix="/components", tags=["components"])


@router.get("/triggers")
def list_triggers(scheduler: Scheduler = Depends(get_core_scheduler)):
    trigger_names = sorted(TRIGGER_PLUGINS)
    return APIResponse(data=[{"name": name} for name in trigger_names])


@router.get("/executors")
def list_executors(scheduler: Scheduler = Depends(get_core_scheduler)):
    executor_names = sorted(EXECUTOR_PLUGINS)
    return APIResponse(data=[{"name": name} for name in executor_names])


@router.get("/executors/configured")
def list_configured_executors(scheduler: Scheduler = Depends(get_core_scheduler)):
    """List persisted executor configurations (same source as jobstores)."""
    result = []
    for alias, cfg in load_executor_configs().items():
        plugin_type = cfg.get("type", "unknown")
        config = {k: v for k, v in cfg.items() if k != "type"}
        job_count = scheduler.count_jobs_by_executor(alias)

        result.append({
            "name": alias,
            "alias": alias,
            "type": plugin_type,
            "config": config if config else None,
            "job_count": job_count,
        })
    return APIResponse(data=result)


@router.get("/jobstores")
def list_jobstores(scheduler: Scheduler = Depends(get_core_scheduler)):
    jobstore_names = sorted(JOBSTORE_PLUGINS)
    return APIResponse(data=[{"name": name} for name in jobstore_names])


@router.post("/jobs/{job_id}/reschedule")
def reschedule_job(job_id: str, request: RescheduleRequest, scheduler: Scheduler = Depends(get_core_scheduler)):
    trigger = Trigger.from_dict({"type": request.trigger, "args": request.trigger_args or {}})
    job = scheduler.reschedule_job(job_id, trigger)
    return APIResponse(data={
        "id": job.job_id,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
    })


# Hardcoded param schemas for known jobstore plugins
_JOBSTORE_PARAM_SCHEMAS: dict[str, list[dict]] = {
    "memory": [],
    "sqlalchemy": [
        {"name": "url", "type": "string", "required": True, "label": "数据库URL", "placeholder": "sqlite:///jobs.db"},
        {"name": "tableschema", "type": "string", "required": False, "label": "表 Schema", "placeholder": "可选"},
        {"name": "engine_options", "type": "json", "required": False, "label": "引擎选项 (JSON)", "placeholder": "{}"},
    ],
    "redis": [
        {"name": "host", "type": "string", "required": False, "label": "主机", "placeholder": "localhost"},
        {"name": "port", "type": "number", "required": False, "label": "端口", "placeholder": "6379"},
        {"name": "db", "type": "number", "required": False, "label": "数据库编号", "placeholder": "0"},
        {"name": "password", "type": "string", "required": False, "label": "密码", "placeholder": "可选"},
    ],
    "mongodb": [
        {"name": "host", "type": "string", "required": False, "label": "主机", "placeholder": "localhost"},
        {"name": "port", "type": "number", "required": False, "label": "端口", "placeholder": "27017"},
        {"name": "database", "type": "string", "required": False, "label": "数据库名", "placeholder": "schedflow"},
        {"name": "collection", "type": "string", "required": False, "label": "集合名", "placeholder": "jobs"},
        {"name": "username", "type": "string", "required": False, "label": "用户名", "placeholder": "可选"},
        {"name": "password", "type": "string", "required": False, "label": "密码", "placeholder": "可选"},
        {"name": "authSource", "type": "string", "required": False, "label": "认证数据库", "placeholder": "admin"},
    ],
}


# Hardcoded param schemas for known executor plugins
_EXECUTOR_PARAM_SCHEMAS: dict[str, list[dict]] = {
    "threadpool": [
        {"name": "max_workers", "type": "number", "required": False, "label": "最大工作线程数", "placeholder": "10"},
    ],
    "processpool": [
        {"name": "max_workers", "type": "number", "required": False, "label": "最大工作进程数", "placeholder": "10"},
    ],
    "asyncio": [],
    "debug": [],
    "gevent": [],
    "tornado": [],
    "twisted": [],
}


@router.get("/jobstores/plugins")
def list_jobstore_plugins(scheduler: Scheduler = Depends(get_core_scheduler)):
    plugin_names = sorted(JOBSTORE_PLUGINS)
    result = []
    for name in plugin_names:
        params = _JOBSTORE_PARAM_SCHEMAS.get(name)
        result.append({"name": name, "params": params if params is not None else []})
    return APIResponse(data=result)


@router.get("/jobstores/configured")
def list_configured_jobstores(scheduler: Scheduler = Depends(get_core_scheduler)):
    configs = load_jobstore_configs()
    result = []
    for alias, cfg in configs.items():
        job_count = scheduler.count_jobs_by_jobstore(alias)
        result.append({
            "alias": alias,
            "type": cfg.get("type", "memory"),
            "job_count": job_count,
        })
    return APIResponse(data=result)


@router.post("/jobstores/configure/{alias}")
def configure_jobstore(
    alias: str,
    request: JobstoreConfigureRequest,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    config = dict(request.config)
    scheduler.add_jobstore(request.type, alias, **config)
    save_jobstore_config(alias, request.type, config)
    return APIResponse(message=f"Jobstore '{alias}' configured")


@router.put("/jobstores/configure/{alias}")
def update_jobstore(
    alias: str,
    request: JobstoreConfigureRequest,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    config = dict(request.config)

    # Read old config BEFORE writing new one
    old_cfg = get_jobstore_config(alias)
    old_type = old_cfg.get("type", "unknown") if old_cfg else "unknown"

    try:
        needs_migration, affected = scheduler._check_jobstore_migration_needed(
            alias, request.type, config
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Jobstore '{alias}' not found")

    # Validate new plugin type by creating a test instance
    scheduler.update_jobstore(request.type, alias, **config)

    # Persist the new config
    update_jobstore_config(alias, request.type, config)

    msg = "存储器配置已更新"
    if needs_migration:
        msg = f"配置已保存，检测到 {affected} 个任务需要迁移到新存储"

    return APIResponse(
        data=JobstoreUpdateResponse(
            alias=alias,
            plugin_type=request.type,
            config=config,
            needs_migration=needs_migration,
            affected_jobs_count=affected,
            old_plugin_type=old_type,
            message=msg,
        ).model_dump()
    )


@router.post("/jobstores/configure/{alias}/migrate")
def migrate_jobstore(
    alias: str,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    try:
        count = scheduler.migrate_jobstore(alias)
        return APIResponse(
            data=JobstoreMigrateResponse(
                alias=alias,
                migrated_count=count,
                message=f"迁移成功，{count} 个任务已迁移到新的存储后端",
            ).model_dump()
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/jobstores/configure/{alias}")
def remove_jobstore(alias: str, scheduler: Scheduler = Depends(get_core_scheduler)):
    try:
        scheduler.remove_jobstore(alias)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    remove_jobstore_config(alias)
    return APIResponse(message=f"Jobstore '{alias}' removed")


@router.get("/jobstores/configured/{alias}")
def get_configured_jobstore(alias: str, scheduler: Scheduler = Depends(get_core_scheduler)):
    cfg = get_jobstore_config(alias)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Jobstore '{alias}' not found")
    plugin_type = cfg.pop("type")
    return APIResponse(data={
        "alias": alias,
        "type": plugin_type,
        "config": cfg,
    })


@router.get("/executors/plugins")
def list_executor_plugins(scheduler: Scheduler = Depends(get_core_scheduler)):
    plugin_names = sorted(EXECUTOR_PLUGINS)
    result = []
    for name in plugin_names:
        params = _EXECUTOR_PARAM_SCHEMAS.get(name)
        result.append({"name": name, "params": params if params is not None else []})
    return APIResponse(data=result)


@router.post("/executors/configure/{alias}")
def configure_executor(
    alias: str,
    request: ExecutorConfigureRequest,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    config = dict(request.config)
    scheduler.add_executor(request.type, alias, **config)
    save_executor_config(alias, request.type, config)
    return APIResponse(message=f"Executor '{alias}' configured")


@router.put("/executors/configure/{alias}")
def update_executor(
    alias: str,
    request: ExecutorConfigureRequest,
    scheduler: Scheduler = Depends(get_core_scheduler),
):
    config = dict(request.config)
    try:
        type_changed = scheduler.update_executor(request.type, alias, **config)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Executor '{alias}' not found")
    save_executor_config(alias, request.type, config)

    msg = "执行器配置已更新"
    if type_changed:
        msg = f"执行器类型已从原有类型变更为 {request.type}，配置已更新"

    return APIResponse(
        data=ExecutorUpdateResponse(
            alias=alias,
            plugin_type=request.type,
            config=config,
            type_changed=type_changed,
            message=msg,
        ).model_dump()
    )


@router.delete("/executors/configure/{alias}")
def remove_executor(alias: str, scheduler: Scheduler = Depends(get_core_scheduler)):
    try:
        scheduler.remove_executor(alias)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    remove_executor_config(alias)
    return APIResponse(message=f"Executor '{alias}' removed")
