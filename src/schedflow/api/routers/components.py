import inspect

from fastapi import APIRouter, Depends, HTTPException

from schedflow.api.deps import get_core_scheduler
from schedflow.api.schemas import (
    APIResponse,
    ExecutorConfigureRequest,
    ExecutorUpdateResponse,
    JobstoreConfigureRequest,
    JobstoreMigrateResponse,
    JobstoreUpdateResponse,
    RescheduleRequest,
)
from schedflow.api.timezone import with_default_timezone
from schedflow.api.trigger_validation import ensure_schedulable
from schedflow.configs.config import (
    get_jobstore_config,
    load_executor_configs,
    load_jobstore_configs,
    remove_executor_config,
    remove_jobstore_config,
    save_executor_config,
    save_jobstore_config,
    update_jobstore_config,
)
from schedflow.core.plugins import EXECUTOR_PLUGINS, JOBSTORE_PLUGINS
from schedflow.core.scheduler import Scheduler
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
    payload = with_default_timezone(
        {"type": request.trigger, "args": request.trigger_args or {}}
    )
    trigger = Trigger.from_dict(ensure_schedulable(payload))
    job = scheduler.reschedule_job(job_id, trigger)
    return APIResponse(data={
        "id": job.job_id,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
    })


# Hardcoded param schemas for known jobstore plugins.
#
# These fields are the contract the frontend renders, so every ``name`` here
# must be an accepted keyword argument of the matching JobStore subclass (see
# tests/test_api_rest/test_frontend_parity.py). The optional ``hint`` key is
# shown as a hover tooltip in the storage configuration form.
_JOBSTORE_PARAM_SCHEMAS: dict[str, list[dict]] = {
    "memory": [],
    "sqlalchemy": [
        {
            "name": "url",
            "type": "string",
            "required": True,
            "label": "数据库URL",
            "placeholder": "sqlite:///data/jobs.db",
            "hint": "SQLAlchemy 连接串。SQLite 示例 sqlite:///data/jobs.db（目录需已存在）；"
                    "其他数据库示例 postgresql://user:密码@主机:5432/库名。",
        },
        {
            "name": "engine_options",
            "type": "json",
            "required": False,
            "label": "引擎选项 (JSON)",
            "placeholder": "{}",
            "hint": "透传给 SQLAlchemy create_engine 的额外参数，JSON 对象，例如 "
                    "{\"pool_pre_ping\": true, \"pool_size\": 5}；留空使用默认值。",
        },
    ],
    "redis": [
        {
            "name": "host",
            "type": "string",
            "required": False,
            "label": "主机",
            "placeholder": "localhost",
            "hint": "Redis 服务地址：本机填 localhost，远程/容器填对应的 IP 或域名。",
        },
        {
            "name": "port",
            "type": "number",
            "required": False,
            "label": "端口",
            "placeholder": "6379",
            "hint": "Redis 监听端口，默认 6379。",
        },
        {
            "name": "db",
            "type": "number",
            "required": False,
            "label": "数据库编号",
            "placeholder": "0",
            "hint": "Redis 逻辑数据库编号（默认 0-15），同一实例内不同编号的数据互相隔离。"
                    "SchedFlow 只占用其中一个，通常填 0 即可。",
        },
        {
            "name": "username",
            "type": "string",
            "required": False,
            "label": "用户名",
            "placeholder": "可选",
            "hint": "Redis 6+ ACL 用户名；使用默认用户时填 default，未启用 ACL 则留空。",
        },
        {
            "name": "password",
            "type": "string",
            "required": False,
            "label": "密码",
            "placeholder": "可选",
            "hint": "Redis 访问密码（requirepass 配置）。服务端未设置密码时留空。",
        },
    ],
    "mongodb": [
        {
            "name": "host",
            "type": "string",
            "required": False,
            "label": "主机",
            "placeholder": "localhost",
            "hint": "MongoDB 服务地址：本机填 localhost，远程/容器填对应的 IP 或域名。",
        },
        {
            "name": "port",
            "type": "number",
            "required": False,
            "label": "端口",
            "placeholder": "27017",
            "hint": "MongoDB 监听端口，默认 27017。",
        },
        {
            "name": "database",
            "type": "string",
            "required": False,
            "label": "数据库名",
            "placeholder": "schedflow",
            "hint": "存放 SchedFlow 数据的数据库名（相当于 MySQL 的库），不存在会自动创建，"
                    "默认 schedflow。",
        },
        {
            "name": "collection",
            "type": "string",
            "required": False,
            "label": "集合名",
            "placeholder": "jobs",
            "hint": "存放任务文档的集合名（相当于关系库的表），默认 jobs；"
                    "执行日志和运行快照会自动使用 jobs_logs、jobs_snapshots 等集合。",
        },
        {
            "name": "username",
            "type": "string",
            "required": False,
            "label": "用户名",
            "placeholder": "可选",
            "hint": "服务端开启鉴权（--auth）时填写 MongoDB 用户名，未开启则留空。",
        },
        {
            "name": "password",
            "type": "string",
            "required": False,
            "label": "密码",
            "placeholder": "可选",
            "hint": "上述用户名对应的密码，未开启鉴权时留空。",
        },
        {
            "name": "authSource",
            "type": "string",
            "required": False,
            "label": "认证数据库",
            "placeholder": "admin",
            "hint": "校验用户名/密码所用的数据库，内置管理员账号通常填 admin；"
                    "留空时由 MongoDB 按连接串默认规则推断。",
        },
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


def _accepted_plugin_options(plugin_cls: type) -> set[str] | None:
    """Return the keyword options ``plugin_cls.__init__`` accepts.

    ``None`` means the constructor declares ``**kwargs`` and therefore accepts
    any option, in which case no validation is possible.
    """
    try:
        parameters = inspect.signature(plugin_cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - exotic/callable objects
        return None
    accepted: set[str] = set()
    for name, parameter in parameters.items():
        if name == "self":
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return None
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            accepted.add(name)
    return accepted


def _ensure_supported_options(
    plugin_cls: type, kind: str, alias: str, config: dict
) -> None:
    """Reject unknown configuration keys with a 400 instead of a 500.

    A stale or buggy frontend field would otherwise reach the plugin
    constructor and surface as ``TypeError: ... unexpected keyword argument``.
    """
    accepted = _accepted_plugin_options(plugin_cls)
    if accepted is None:
        return
    unknown = sorted(set(config) - accepted)
    if unknown:
        supported = ", ".join(sorted(accepted)) or "(none)"
        raise HTTPException(
            status_code=400,
            detail=(
                f"{kind} '{alias}' does not support option(s): "
                f"{', '.join(unknown)}. Supported options: {supported}"
            ),
        )


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
    plugin_cls = JOBSTORE_PLUGINS.get(request.type)
    if plugin_cls is not None:
        _ensure_supported_options(plugin_cls, "Jobstore", alias, config)
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
    plugin_cls = JOBSTORE_PLUGINS.get(request.type)
    if plugin_cls is not None:
        _ensure_supported_options(plugin_cls, "Jobstore", alias, config)

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
