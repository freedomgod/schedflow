# Changelog

## Unreleased (in development)

### Added

- **`Workflow`**: build DAGs with `add_task()/add_edge()`; topological generation-based parallelism, conditional edges, cycle detection (`CycleError`), `_pre_results` injection, retries/timeouts/callbacks, and `to_dict()/from_dict()` as the single JSON serialization path;
- **`TaskSpec`**: four task types `python_callable` / `python` / `python_script` / `bash`, with subprocess env/cwd/timeout support;
- **`ExecutionLog` / `TaskRecord`**: structured execution logs with per-node status, result, error, stdout/stderr, exit code and duration;
- **Explicit triggers**: `DateTrigger` / `IntervalTrigger` / `CronTrigger` (incl. `from_crontab`) / `CalendarIntervalTrigger` / `AndTrigger` / `OrTrigger` with keyword construction and `to_dict()/from_dict()`;
- **`Scheduler`**: unified scheduler (background-thread main loop) with explicit `add_job/update_job/remove_job/pause_job/resume_job/reschedule_job/run_job_now/get_job_logs/get_job_log` and string-based event subscription via `on()`;
- **Event system improvements**: after the scheduler executes a job, per-node `task.executed` / `task.error` / `task.skipped` events are published (`event.record` carries the node's `TaskRecord`, `event.log` the full `ExecutionLog`); new `Scheduler.off()` unsubscribes event callbacks;
- **Unified `JobStore` interface**: `add/update/remove/get/get_due/get_all/get_next_run_time/add_log/get_logs/get_log/close` with `Memory`, `SQLAlchemy`, `Redis` and `MongoDB` implementations, all JSON-serialized;
- **Unified `Executor` interface**: `ThreadPoolExecutor`, `ProcessPoolExecutor` (JSON worker protocol, Windows spawn-ready), `DebugExecutor`;
- **Web API**: full `/api/jobs` CRUD plus run-now/reschedule/logs/scheduler lifecycle, unified `{"code":0,"data":...,"message":"ok"}` responses and 404/409/422 error mapping;
- **Vue 3 dashboard**: dashboard, DAG workflow editor, job list, execution log viewer, executor/store configuration, dark/light themes;
- **CLI entries**: `schedflow-backend` and `schedflow-frontend`.

### Fixes and improvements

- **CLI defaults to production**: `schedflow-backend` / `schedflow-frontend`
  now start with reload disabled and INFO logging; development behaviour is
  only enabled with `--dev`. In development mode the reload watcher excludes
  `jobs.db`, `.git`, `node_modules` and `dist`, so runtime file writes no
  longer spam "changes detected" output;
- **Scheduler re-entry guard**: the next run time is persisted *before* a due
  job is dispatched; a failed store write aborts the dispatch (retried on the
  next loop), fixing the flood of executions caused by transient write errors
  (e.g. SQLite lock contention) leaving `next_run_time` stuck in the past.
  SQLAlchemy store writes now retry short-lived lock conflicts;
- **Node timing fix**: `TaskRecord` is marked started before the node actually
  runs, so per-node durations no longer read 0.

### Requirements

- Python 3.11+
