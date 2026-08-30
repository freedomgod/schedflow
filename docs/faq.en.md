# FAQ

## Workflows and tasks

### Which Python versions are supported?

Python 3.11, 3.12 and 3.13.

### Can I mix task types in one workflow?

Yes. Each node has its own `type`: one node calls a Python function, another runs a `.py` script, a third runs a shell command.

### What happens when a task fails?

Downstream nodes that depend on the failed node are marked `skipped` (with a `skip_reason`); unaffected parallel branches keep running. Nodes can retry with `retries`. If any node is `failed`, `log.succeeded` is `False` and the scheduler publishes `job.failed`.

### How do downstream tasks access upstream results?

Declare the `_pre_results` keyword argument; it receives a `node_id -> result` dict. The framework filters arguments against the signature, so omitting it never causes an error.

### What is the difference between `Workflow("etl")`'s flow_id and `add_job(..., job_id=...)`'s job_id?

They identify different layers:

- `flow_id` is the name of the **workflow definition**. It is optional at creation (defaults to `None`), appears in `ExecutionLog.flow_id` and the `flow_id` field of `Workflow.to_dict()`, and acts as a label — it does **not** need to be unique, so several jobs can share one `flow_id`;
- `job_id` is the **unique key of the scheduled job** in the job store, used by `get_job()` / `update_job()` / `remove_job()` / `pause_job()`, by `event.job_id` in events, and by log lookups (`/api/jobs/{job_id}/logs`); a UUID is generated when it is omitted.

The `ExecutionLog` of a run carries both: `log.flow_id` comes from the workflow and `log.job_id` from the job. A direct `Workflow.run()` has no job, so `log.job_id` is `None`. A typical pattern: register the same workflow (same `flow_id`) as several jobs with different `job_id`s and triggers.

### Can I create circular dependencies?

No. `Workflow.add_edge()` runs cycle detection and raises `CycleError` without adding the edge.

### Why do lambdas or nested functions fail in `func`?

`to_dict()` must turn the function into a string reference for persistence; lambdas and local nested functions have no stable reference and raise `ValueError`. Use `"module:function"` strings for cross-process or persistence scenarios.

### Why don't string references fail at creation time?

References are resolved **lazily at execution time**. This keeps job creation, persistence and restarts independent of whether the target module is importable — a missing module fails only that node's run and is recorded in the `TaskRecord`, instead of silently dropping the job.

## Scheduling and deployment

### How do I persist jobs across scheduler restarts?

Use a persistent store such as `SQLAlchemyJobStore`, `RedisJobStore` or `MongoDBJobStore`, and make sure workflow nodes use string references:

```python
from schedflow.core import Scheduler
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

scheduler = Scheduler(jobstore=SQLAlchemyJobStore(url="sqlite:///data/jobs.db"))
```

### Can I run multiple scheduler instances?

Multiple instances sharing one persistent store see the same job definitions, but there is **no built-in distributed locking** — make sure the same job is not triggered by multiple instances (e.g. split jobs per instance or run the scheduler on a primary instance only).

### Why does the backend print lots of "X changes detected"?

That output comes from uvicorn's **reload watcher** (watchfiles). The default
startup is production mode (`RELOAD=false`), which does not watch the
filesystem; hot reload is only enabled with `schedflow-backend --dev`. In
  development mode, paths that change constantly at runtime are excluded from
  the watcher (`data/jobs.db`, `*.db-journal`, `.git/**`, `node_modules/**`,
  `dist/**`), so data/jobs.db writes and Git fsmonitor cookies no longer spam
  that output.

Hot reload also rebuilds the scheduler process on code changes; if an old
  process does not exit cleanly, several schedulers may write the same
  `data/jobs.db` at once and duplicate executions can occur (one of the
  triggers behind the earlier "dozens of runs in seconds" bug). **For
  production, run `uv run schedflow-backend` without `--dev` and keep exactly
  one backend process alive.**

### Does the process pool work on Windows?

Yes. `ProcessPoolExecutor` rebuilds the job in child processes via a JSON worker protocol (spawn) instead of pickling the scheduler/function objects. Nodes must use string references and their results must be JSON-serializable.

### My job did not run at the expected time

- confirm the scheduler was `start()`ed and is not `paused`;
- check the job's `next_run_time` and trigger configuration;
- check whether `misfire_grace_time` was exceeded (late runs are skipped with a `job.missed` event);
- check whether `max_instances` was reached (publishes `job.max_instances`);
- inspect `get_job_logs()` to find the failing node.

### I subscribed to `scheduler.on("task.executed", ...)` but nothing prints?

Check two things:

- **the job must actually run through the scheduler** — `task.*` events are published only on the scheduler execution path (scheduled runs or `run_job_now()`). Calling `Workflow.run()` directly bypasses the scheduler and publishes no events; read the returned `ExecutionLog` instead;
- **subscribe on the same scheduler** — each `Scheduler` owns an independent `EventBus`; `scheduler.on(...)` only receives events published by that scheduler. Subscribing on a standalone `EventBus()` and expecting another scheduler's events will also yield nothing.

## Web API and frontend

### How do I enable authentication?

The Web API (`create_app`) has no auth by default; attach `AuthMiddleware` manually with the built-in `JWTBackend`/`APIKeyBackend` or a custom `AuthBackend` — see the Authentication section of [Advanced Usage](user-guide/advanced-usage.md).

### Does the frontend support mobile?

The Vue 3 dashboard is responsive for tablet and desktop via Element Plus and custom CSS; mobile optimization is not finished.

### Does the Web API have SSE?

Not yet. The Web API offers log query endpoints for polling, or you can implement push from the SDK events.

## Documentation and builds

### Why does `mkdocs serve` show the "Material for MkDocs / MkDocs 2.0" warning?

That is an **informational announcement** from the Material theme about the upcoming MkDocs 2.0; it does not affect the current build or usage. This repository pins the MkDocs 1.x series and builds normally.

### Why does the doc build ask for Black or Ruff?

`mkdocstrings` needs one of them to format function signatures. Installing `.[doc]` (which includes `ruff`) removes the message.

### Why is the English URL a nested path like `/zh-cn/latest/en/`?

Two layers stack: Read the Docs prefixes the URL with the project language (`/zh-cn/latest/` here), while mkdocs-static-i18n puts English under `/en/` inside the site, so the English URL becomes `/zh-cn/latest/en/`. The `/zh-cn/` prefix comes from the RTD project language setting and cannot be removed; under local `mkdocs serve` there is no prefix (Chinese at the root, English at `/en/`). Switcher links are page-relative and work both locally and on Read the Docs. If links still 404, confirm the RTD project language is "Chinese (Simplified)" and that the latest build succeeded.
