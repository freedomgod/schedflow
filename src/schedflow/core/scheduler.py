"""Scheduler with an explicit API and a unified main loop."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tzlocal import get_localzone

from schedflow.core.events import EventBus, SchedulerEvent
from schedflow.core.executor import ThreadPoolExecutor
from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobNotFoundError,
    MemoryJobStore,
)
from schedflow.core.plugins import EXECUTOR_PLUGINS, JOBSTORE_PLUGINS
from schedflow.core.workflow import Workflow
from schedflow.triggers.base import Trigger
from schedflow.utils import astimezone

if TYPE_CHECKING:
    from schedflow.core.executor import Executor
    from schedflow.core.jobstore import JobStore
    from schedflow.core.log import ExecutionLog

STATE_STOPPED = 0
STATE_RUNNING = 1
STATE_PAUSED = 2

#: Connection parameters that, when changed for the same plugin type, make a
#: jobstore data migration necessary (mirrors the legacy components contract).
_JOBSTORE_CONNECTION_PARAMS: dict[str, set[str]] = {
    "memory": set(),
    "sqlalchemy": {"url"},
    "redis": {"host", "port", "db"},
    "mongodb": {"host", "port", "database", "collection"},
}


class Scheduler:
    """Schedules workflows with triggers and executes them via executors.

    Usage::

        scheduler = Scheduler()
        scheduler.add_job(
            workflow,
            trigger=IntervalTrigger(seconds=60),
            job_id="my_job",
        )
        scheduler.start()
        ...
        scheduler.shutdown()
    """

    def __init__(
        self,
        *,
        jobstore: JobStore | None = None,
        executor: Executor | None = None,
        timezone=None,
        project_root: str | Path | None = None,
        job_defaults: dict | None = None,
    ) -> None:
        self._jobstore = jobstore or MemoryJobStore()
        self._executor = executor or ThreadPoolExecutor()
        self._jobstores: dict[str, JobStore] = {"default": self._jobstore}
        self._executors: dict[str, Executor] = {"default": self._executor}
        self._timezone = astimezone(timezone) if timezone is not None else get_localzone()
        self._project_root = (
            Path(project_root) if project_root is not None else None
        )
        self._job_defaults = job_defaults or {}
        self._events = EventBus()
        self.state = STATE_STOPPED
        self._lock = threading.RLock()
        self._running: dict[str, int] = {}
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── component management ────────────────────────────────────────────

    def set_jobstore(self, jobstore: JobStore, alias: str = "default") -> None:
        self._jobstores[alias] = jobstore
        if alias == "default":
            self._jobstore = jobstore

    def set_executor(self, executor: Executor, alias: str = "default") -> None:
        self._executors[alias] = executor
        if alias == "default":
            self._executor = executor
        if self.state != STATE_STOPPED:
            executor.start(self)

    def add_executor(
        self, executor: str | Executor, alias: str = "default", **executor_opts
    ) -> Executor:
        """Add an executor by plugin name or instance under the given alias."""
        with self._lock:
            if alias in self._executors:
                raise ValueError(
                    f'This scheduler already has an executor by the alias of "{alias}"'
                )
            instance = self._resolve_plugin(
                executor, executor_opts, EXECUTOR_PLUGINS, "executor"
            )
            self._executors[alias] = instance
            if alias == "default":
                self._executor = instance
        if self.state != STATE_STOPPED:
            instance.start(self)
        return instance

    def remove_executor(
        self, alias: str, shutdown: bool = True, force: bool = False
    ) -> None:
        """Remove an executor; refuses when jobs still reference it."""
        if alias == "default":
            raise RuntimeError("Cannot remove the default executor")
        if not force:
            ref_count = self.count_jobs_by_executor(alias)
            if ref_count > 0:
                raise RuntimeError(
                    f"Executor '{alias}' is referenced by {ref_count} job(s)"
                )
        with self._lock:
            executor = self._lookup_executor(alias)
            del self._executors[alias]
        if shutdown:
            executor.shutdown()

    def update_executor(
        self, executor: str | Executor, alias: str = "default", **executor_opts
    ) -> bool:
        """Replace an executor; returns True when the plugin type changed."""
        with self._lock:
            if alias not in self._executors:
                raise KeyError(f"No such executor: {alias}")
            old = self._executors[alias]
            old_type = self._plugin_name_for_instance(old, EXECUTOR_PLUGINS)
            new_type = (
                executor if isinstance(executor, str) else type(executor).__name__
            )
            type_changed = old_type != new_type
            if self.state != STATE_STOPPED:
                old.shutdown()
            instance = self._resolve_plugin(
                executor, executor_opts, EXECUTOR_PLUGINS, "executor"
            )
            self._executors[alias] = instance
            if alias == "default":
                self._executor = instance
        if self.state != STATE_STOPPED:
            instance.start(self)
        return type_changed

    def get_executor(self, alias: str) -> Executor:
        if alias not in self._executors:
            raise KeyError(f"No such executor: {alias}")
        return self._executors[alias]

    def _lookup_executor(self, alias: str) -> Executor:
        try:
            return self._executors[alias]
        except KeyError:
            raise KeyError(f"No such executor: {alias}") from None

    def add_jobstore(
        self, jobstore: str | JobStore, alias: str = "default", **jobstore_opts
    ) -> JobStore:
        """Add a jobstore by plugin name or instance under the given alias."""
        with self._lock:
            if alias in self._jobstores:
                raise ValueError(
                    f'This scheduler already has a job store by the alias of "{alias}"'
                )
            instance = self._resolve_plugin(
                jobstore, jobstore_opts, JOBSTORE_PLUGINS, "jobstore"
            )
            self._jobstores[alias] = instance
            if alias == "default":
                self._jobstore = instance
        self.wakeup()
        return instance

    def remove_jobstore(
        self, alias: str, shutdown: bool = True, force: bool = False
    ) -> None:
        """Remove a jobstore; refuses when it still contains jobs."""
        if alias == "default":
            raise RuntimeError("Cannot remove the default jobstore")
        if not force:
            count = self.count_jobs_by_jobstore(alias)
            if count > 0:
                raise RuntimeError(
                    f"Jobstore '{alias}' contains {count} job(s). "
                    f"Migrate or delete the jobs first."
                )
        with self._lock:
            jobstore = self._lookup_jobstore(alias)
            del self._jobstores[alias]
        if shutdown:
            jobstore.close()

    def update_jobstore(
        self, jobstore: str | JobStore, alias: str = "default", **jobstore_opts
    ) -> None:
        """Validate a new jobstore configuration without replacing the live store.

        The actual replacement happens in ``migrate_jobstore(alias)`` (mirrors the
        legacy components contract).
        """
        with self._lock:
            if alias not in self._jobstores:
                raise KeyError(f"No such jobstore: {alias}")
            self._resolve_plugin(jobstore, jobstore_opts, JOBSTORE_PLUGINS, "jobstore")

    def get_jobstore(self, alias: str) -> JobStore:
        if alias not in self._jobstores:
            raise KeyError(f"No such jobstore: {alias}")
        return self._jobstores[alias]

    def _lookup_jobstore(self, alias: str) -> JobStore:
        try:
            return self._jobstores[alias]
        except KeyError:
            raise KeyError(f"No such jobstore: {alias}") from None

    def _resolve_plugin(
        self, spec: str | object, opts: dict, registry: dict[str, type], kind: str
    ) -> object:
        if isinstance(spec, str):
            plugin_cls = registry.get(spec)
            if plugin_cls is None:
                raise ValueError(
                    f"Unknown {kind} plugin {spec!r}; available: {sorted(registry)}"
                )
            return plugin_cls(**opts)
        return spec

    def _plugin_name_for_instance(self, instance, registry: dict[str, type]) -> str:
        for name, plugin_cls in registry.items():
            if isinstance(instance, plugin_cls):
                return name
        return type(instance).__name__

    def count_jobs_by_jobstore(self, alias: str) -> int:
        jobstore = self._jobstores.get(alias)
        if jobstore is None:
            return 0
        return len(jobstore.get_all())

    def count_jobs_by_executor(self, alias: str) -> int:
        return sum(
            1 for job in self.get_jobs() if job.executor_alias == alias
        )

    def _count_jobs_by_jobstore(self, alias: str) -> int:
        return self.count_jobs_by_jobstore(alias)

    def _count_jobs_by_executor(self, alias: str) -> int:
        return self.count_jobs_by_executor(alias)

    def _check_jobstore_migration_needed(
        self, alias: str, new_plugin_type: str, new_config: dict
    ) -> tuple[bool, int]:
        """Mirror of the legacy components check: type change or connection change."""
        from schedflow.configs.config import get_jobstore_config

        with self._lock:
            old_instance = self._jobstores.get(alias)
            if old_instance is None:
                raise KeyError(f"No such jobstore: {alias}")
        old_plugin_type = self._plugin_name_for_instance(
            old_instance, JOBSTORE_PLUGINS
        )
        old_cfg = get_jobstore_config(alias) or {}
        if old_plugin_type != new_plugin_type:
            needs = True
        else:
            key_params = _JOBSTORE_CONNECTION_PARAMS.get(new_plugin_type, set())
            needs = any(
                new_config.get(param) != old_cfg.get(param)
                for param in key_params
            )
        affected = 0
        if needs:
            try:
                affected = len(old_instance.get_all())
            except Exception:  # noqa: BLE001
                affected = -1
        return needs, affected

    def migrate_jobstore(self, source: str, target: str | None = None) -> int:
        """Move jobs between jobstores.

        Two-argument form moves jobs from ``source`` into an already registered
        ``target`` store. One-argument form (legacy components contract) replaces
        the store at ``alias`` with the instance built from its persisted config.
        """
        if target is None:
            return self._migrate_jobstore_from_config(source)
        src = self.get_jobstore(source)
        dst = self.get_jobstore(target)
        jobs = src.get_all()
        with self._lock:
            for job in jobs:
                job.jobstore_alias = target
                dst.add(job)
                src.remove(job.job_id)
        return len(jobs)

    def _migrate_jobstore_from_config(self, alias: str) -> int:
        from schedflow.configs.config import get_jobstore_config

        new_cfg = get_jobstore_config(alias)
        if new_cfg is None:
            raise KeyError(f"No persisted config for jobstore: {alias}")
        plugin_type = new_cfg.get("type", "memory")
        plugin_config = {k: v for k, v in new_cfg.items() if k != "type"}
        with self._lock:
            old_instance = self._jobstores.get(alias)
            if old_instance is None:
                raise KeyError(f"No such jobstore: {alias}")
            new_instance = self._resolve_plugin(
                plugin_type, plugin_config, JOBSTORE_PLUGINS, "jobstore"
            )
            try:
                jobs = old_instance.get_all()
                for job in jobs:
                    new_instance.add(job)
            except Exception as exc:
                new_instance.close()
                raise RuntimeError(
                    f"Migration failed: {exc}. The old store is still intact, "
                    f"please check the new store configuration and retry."
                ) from exc
            old_instance.close()
            self._jobstores[alias] = new_instance
            if alias == "default":
                self._jobstore = new_instance
        self.wakeup()
        return len(jobs)

    def wakeup(self) -> None:
        """Interrupt the main loop's idle wait so it re-scans immediately."""
        self._wakeup_event.set()

    def on(self, kind: str, callback: Callable[[SchedulerEvent], None]) -> None:
        """Subscribe to an event kind (see core.events.EVENT_KINDS)."""
        self._events.subscribe(kind, callback)

    def off(
        self, kind: str, callback: Callable[[SchedulerEvent], None]
    ) -> None:
        """Unsubscribe a previously registered event callback."""
        self._events.unsubscribe(kind, callback)

    # ── job management ──────────────────────────────────────────────────

    def add_job(
        self,
        workflow: Workflow | dict,
        *,
        trigger: Trigger | None = None,
        job_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        executor_alias: str = "default",
        jobstore_alias: str = "default",
        misfire_grace_time: int | None = None,
        coalesce: bool = True,
        max_instances: int = 1,
        replace: bool = False,
    ) -> Job:
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)
        if not isinstance(workflow, Workflow):
            raise TypeError("workflow must be a Workflow instance or its JSON dict")
        if trigger is not None and not hasattr(trigger, "get_next_fire_time"):
            raise TypeError(
                "trigger must provide get_next_fire_time(previous, now) or be None"
            )
        if (
            self._project_root is not None
            and workflow.project_root is None
        ):
            workflow.project_root = self._project_root
        job = Job(
            workflow,
            trigger,
            job_id=job_id,
            name=name,
            description=description,
            executor_alias=executor_alias,
            jobstore_alias=jobstore_alias,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce,
            max_instances=max_instances,
        )
        store = self.get_jobstore(jobstore_alias)
        with self._lock:
            if replace and store.get(job.job_id) is not None:
                store.update(job)
            else:
                store.add(job)
        self._events.publish(SchedulerEvent("job.added", job_id=job.job_id))
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._find_job(job_id)

    def get_jobs(self, jobstore_alias: str | None = None) -> list[Job]:
        with self._lock:
            if jobstore_alias is None:
                return [
                    job
                    for jobstore in self._jobstores.values()
                    for job in jobstore.get_all()
                ]
            return self.get_jobstore(jobstore_alias).get_all()

    def _find_job(self, job_id: str) -> Job | None:
        """Locate a job across all registered jobstores."""
        for jobstore in self._jobstores.values():
            job = jobstore.get(job_id)
            if job is not None:
                return job
        return None

    def update_job(
        self,
        job_id: str,
        *,
        name=None,
        description=None,
        workflow=None,
        trigger=None,
        executor_alias=None,
        jobstore_alias=None,
        misfire_grace_time=None,
        coalesce=None,
        max_instances=None,
    ) -> Job:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            old_alias = job.jobstore_alias
            if name is not None:
                job.name = name
            if description is not None:
                job.description = description
            if workflow is not None:
                if isinstance(workflow, dict):
                    workflow = Workflow.from_dict(workflow)
                if not isinstance(workflow, Workflow):
                    raise TypeError("workflow must be a Workflow or its JSON dict")
                job.workflow = workflow
            if trigger is not None:
                if not hasattr(trigger, "get_next_fire_time"):
                    raise TypeError(
                        "trigger must provide get_next_fire_time(previous, now)"
                    )
                job.trigger = trigger
                job.next_run_time = trigger.get_next_fire_time(
                    None, datetime.now(self._timezone)
                )
            if executor_alias is not None:
                job.executor_alias = executor_alias
            if jobstore_alias is not None:
                job.jobstore_alias = jobstore_alias
            if misfire_grace_time is not None:
                job.misfire_grace_time = misfire_grace_time
            if coalesce is not None:
                job.coalesce = bool(coalesce)
            if max_instances is not None:
                job.max_instances = max(1, int(max_instances))
            if job.jobstore_alias != old_alias:
                old_store = self._jobstores.get(old_alias, self._jobstore)
                try:
                    old_store.remove(job.job_id)
                except JobNotFoundError:
                    pass
                self.get_jobstore(job.jobstore_alias).add(job)
            else:
                store = self._jobstores.get(job.jobstore_alias, self._jobstore)
                store.update(job)
        self._events.publish(SchedulerEvent("job.updated", job_id=job_id))
        return job

    def remove_job(self, job_id: str) -> None:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
            store.remove(job_id)
        self._events.publish(SchedulerEvent("job.removed", job_id=job_id))

    def pause_job(self, job_id: str) -> Job:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.status = "paused"
            job.next_run_time = None
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
            store.update(job)
        self._events.publish(SchedulerEvent("job.paused", job_id=job_id))
        return job

    def resume_job(self, job_id: str) -> Job:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.status = "running"
            job.next_run_time = (
                job.trigger.get_next_fire_time(
                    None, datetime.now(self._timezone)
                )
                if job.trigger is not None
                else None
            )
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
            store.update(job)
        self._events.publish(SchedulerEvent("job.resumed", job_id=job_id))
        return job

    def reschedule_job(self, job_id: str, trigger: Trigger) -> Job:
        return self.update_job(job_id, trigger=trigger)

    def run_job_now(self, job_id: str, *, max_workers: int = 3) -> ExecutionLog:
        with self._lock:
            job = self._find_job(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
        self._events.publish(
            SchedulerEvent("job.started", job_id=job_id)
        )
        try:
            log = job.run(max_workers=max_workers)
        except Exception:
            self._events.publish(SchedulerEvent("job.failed", job_id=job_id))
            raise
        with self._lock:
            store.add_log(job_id, log)
        self._publish_task_events(job_id, None, log)
        kind = "job.succeeded" if log.succeeded else "job.failed"
        self._events.publish(
            SchedulerEvent(kind, job_id=job_id, log=log)
        )
        return log

    def get_job_logs(self, job_id: str) -> list[ExecutionLog]:
        with self._lock:
            logs: list[ExecutionLog] = []
            for jobstore in self._jobstores.values():
                logs.extend(jobstore.get_logs(job_id))
            return logs

    def get_job_log(self, job_id: str, log_id: str) -> ExecutionLog | None:
        with self._lock:
            for jobstore in self._jobstores.values():
                log = jobstore.get_log(job_id, log_id)
                if log is not None:
                    return log
            return None

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self, paused: bool = False) -> None:
        if self.state != STATE_STOPPED:
            raise ValueError("Scheduler is already running")
        for executor in self._executors.values():
            executor.start(self)
        self.state = STATE_PAUSED if paused else STATE_RUNNING
        self._stop_event.clear()
        self._wakeup_event.clear()
        self._thread = threading.Thread(
            target=self._main_loop,
            name="schedflow",
            daemon=True,
        )
        self._thread.start()
        self._events.publish(SchedulerEvent("scheduler.started"))

    def pause(self) -> None:
        if self.state == STATE_STOPPED:
            raise ValueError("Scheduler is not running")
        self.state = STATE_PAUSED
        self._events.publish(SchedulerEvent("scheduler.paused"))

    def resume(self) -> None:
        if self.state == STATE_STOPPED:
            raise ValueError("Scheduler is not running")
        self.state = STATE_RUNNING
        self._wakeup_event.set()
        self._events.publish(SchedulerEvent("scheduler.resumed"))

    def shutdown(self, *, wait: bool = True) -> None:
        if self.state == STATE_STOPPED:
            return
        self._stop_event.set()
        self._wakeup_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10 if wait else 0)
        for executor in self._executors.values():
            executor.shutdown(wait=wait)
        self.state = STATE_STOPPED
        self._events.publish(SchedulerEvent("scheduler.shutdown"))

    # ── main loop ───────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.state == STATE_RUNNING:
                try:
                    self._process_due()
                except Exception:  # noqa: BLE001, S110 - loop must keep running
                    pass
            with self._lock:
                next_run = None
                for jobstore in self._jobstores.values():
                    candidate = jobstore.get_next_run_time()
                    if candidate is not None and (
                        next_run is None or candidate < next_run
                    ):
                        next_run = candidate
            if self.state == STATE_PAUSED or next_run is None:
                wait_seconds = 1.0
            else:
                wait_seconds = min(
                    max(
                        (next_run - datetime.now(self._timezone)).total_seconds(),
                        0,
                    ),
                    60,
                )
            self._wakeup_event.clear()
            self._wakeup_event.wait(wait_seconds)

    def _process_due(self) -> None:
        now = datetime.now(self._timezone)
        due = []
        with self._lock:
            for jobstore in self._jobstores.values():
                due.extend(jobstore.get_due(now))
        for job in due:
            self._run_due_job(job, now)

    def _run_due_job(self, job: Job, now: datetime) -> None:
        run_time = job.next_run_time
        if (
            job.misfire_grace_time is not None
            and (now - run_time).total_seconds() > job.misfire_grace_time
        ):
            self._events.publish(
                SchedulerEvent("job.missed", job_id=job.job_id, run_time=run_time)
            )
            self._advance(job, run_time, now)
            return
        count = self._running.get(job.job_id, 0)
        if count >= job.max_instances:
            self._events.publish(
                SchedulerEvent(
                    "job.max_instances", job_id=job.job_id, run_time=run_time
                )
            )
            return
        # Persist the next fire time BEFORE dispatching the run. If the store
        # write fails (e.g. transient SQLite lock contention), the exception
        # aborts the dispatch instead of leaving next_run_time in the past,
        # which would otherwise re-fire the job back-to-back and flood the
        # store with executions.
        self._advance(job, run_time, now)
        self._running[job.job_id] = count + 1
        self._events.publish(
            SchedulerEvent("job.started", job_id=job.job_id, run_time=run_time)
        )
        executor = self._executors.get(job.executor_alias, self._executor)
        executor.submit(job, run_time)

    def _advance(self, job: Job, run_time: datetime, now: datetime) -> None:
        store = self._jobstores.get(job.jobstore_alias, self._jobstore)
        if job.trigger is None:
            job.next_run_time = None
        else:
            next_run = job.trigger.get_next_fire_time(run_time, now)
            if next_run is None:
                try:
                    store.remove(job.job_id)
                except JobNotFoundError:
                    pass
                self._events.publish(
                    SchedulerEvent("job.removed", job_id=job.job_id)
                )
                return
            job.next_run_time = next_run
        try:
            store.update(job)
        except JobNotFoundError:
            pass

    def _on_job_finished(
        self,
        job: Job,
        run_time: datetime,
        log: ExecutionLog | None,
        error: Exception | None = None,
    ) -> None:
        count = self._running.get(job.job_id, 1) - 1
        if count <= 0:
            self._running.pop(job.job_id, None)
        else:
            self._running[job.job_id] = count
        if log is not None:
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
            with self._lock:
                store.add_log(job.job_id, log)
            self._publish_task_events(job.job_id, run_time, log)
            kind = "job.succeeded" if log.succeeded else "job.failed"
            self._events.publish(
                SchedulerEvent(kind, job_id=job.job_id, run_time=run_time, log=log)
            )
        elif error is not None:
            from schedflow.core.log import ExecutionLog, TaskRecord

            now = datetime.now(self._timezone)
            log = ExecutionLog(
                flow_id=getattr(job.workflow, "flow_id", None) or job.job_id,
                job_id=job.job_id,
                start_time=now,
            )
            nodes: list[dict] = []
            if hasattr(job.workflow, "to_dict"):
                nodes = job.workflow.to_dict().get("nodes") or []
            for node in nodes:
                node_id = node.get("node_id", "unknown")
                log.records[node_id] = TaskRecord(
                    node_id=node_id,
                    status="failed",
                    error=str(error),
                    start_time=now,
                    end_time=now,
                )
            log.finalize()
            store = self._jobstores.get(job.jobstore_alias, self._jobstore)
            with self._lock:
                store.add_log(job.job_id, log)
            self._publish_task_events(job.job_id, run_time, log)
            self._events.publish(
                SchedulerEvent(
                    "job.failed",
                    job_id=job.job_id,
                    run_time=run_time,
                    log=log,
                )
            )

    def _publish_task_events(
        self,
        job_id: str,
        run_time: datetime | None,
        log: ExecutionLog,
    ) -> None:
        """Publish one task.* event per node recorded in the execution log."""
        for record in log.records.values():
            if record.status == "succeeded":
                kind = "task.executed"
            elif record.status == "failed":
                kind = "task.error"
            elif record.status == "skipped":
                kind = "task.skipped"
            else:
                continue
            self._events.publish(
                SchedulerEvent(
                    kind,
                    job_id=job_id,
                    run_time=run_time,
                    log=log,
                    record=record,
                )
            )
