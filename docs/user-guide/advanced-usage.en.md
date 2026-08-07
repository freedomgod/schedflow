# Advanced Usage

## Retries, timeouts and callbacks

`Workflow.add_task()` supports per-node retry counts, per-attempt timeouts and success/failure callbacks:

```python
def flaky_func() -> str:
    return "ok"


def on_success(retval):
    print("succeeded:", retval)


def on_failure(error):
    print("failed:", error)


wf.add_task(
    "flaky",
    func=flaky_func,
    retries=3,              # at most 3 attempts (including the first)
    timeout=10,             # per-attempt timeout in seconds
    on_success=on_success,  # receives the task return value
    on_failure=on_failure,  # receives the error message string
)
```

Behavior:

- a node is marked `failed` only after all retries are exhausted;
- the timeout applies per attempt (callables run in a dedicated thread; subprocess tasks pass it through to `subprocess`);
- callback failures do not affect the task result (callbacks run after the node status is recorded).

## Conditional edges in depth

A condition receives the **upstream node's `TaskRecord`** (not the raw return value) and returns `True` to allow or `False` to skip:

```python
def high_value(record) -> bool:
    return bool(record.result) and record.result.get("value", 0) > 100


wf.add_edge("fetch", "transform", condition=high_value)
```

With multiple predecessors, **all** of them must succeed and all incoming condition edges must be satisfied; otherwise the node is skipped. Predecessor results are injected as `_pre_results` (node ID → return value):

```python
def combine(_pre_results):
    left = _pre_results["left"]
    right = _pre_results["right"]
    return left + right
```

## Function references and project_root

`func` accepts a callable or a string reference. String references are resolved **only at execution time** and support three forms:

```python
wf.add_task("a", func="my_package.tasks:fetch")         # importable module
wf.add_task("b", func="./tasks/hello.py:main")          # path relative to project_root
wf.add_task("c", func="D:/proj/tasks/hello.py:main")    # absolute path (Windows drives handled)
```

The base directory comes from `Workflow(project_root=...)` or `Scheduler(project_root=...)` (defaults to the process cwd). Failed resolutions raise `RefResolveError` whose message lists every attempted path:

```text
Could not resolve reference 'my_package.tasks:fetch'. Attempted: file D:\proj\my_package\tasks; file D:\proj\my_package\tasks.py; import 'my_package.tasks' via sys.path
```

!!! tip "Why lazy resolution"
    Creating, persisting or restarting a job never resolves references — only executing the node does. A temporarily missing module fails that node's run and is recorded in the `TaskRecord` instead of silently dropping the job.

## Process-pool executor

```python
from schedflow.core import Scheduler
from schedflow.core.executor import ProcessPoolExecutor

scheduler = Scheduler(executor=ProcessPoolExecutor(max_workers=4))
```

`ProcessPoolExecutor` uses a **JSON worker protocol**: the parent sends only `Job.to_dict()` (pure JSON), the child rebuilds the job with `Job.from_dict()` and runs it, then returns the `ExecutionLog` JSON. Therefore:

- it works on Windows (spawn);
- workflow nodes must use **string references** (importable modules or script paths) — no closures, lambdas or nested functions;
- node results must be JSON-serializable or log persistence fails.

## Serialization contract (single JSON path)

All persistence uses JSON with one serialization interface: `to_dict()/from_dict()`.

```python
from schedflow.triggers.base import Trigger

data = workflow.to_dict()                # Workflow JSON
wf2 = Workflow.from_dict(data)

data = job.to_dict()                     # Job JSON (workflow, trigger, metadata)
job2 = Job.from_dict(data)

data = trigger.to_dict()                 # {"type": "interval", "args": {...}}
trigger2 = Trigger.from_dict(data)
```

`Workflow.to_dict()` structure:

```json
{
  "flow_id": "etl",
  "project_root": null,
  "nodes": [
    {
      "node_id": "fetch",
      "task": {"type": "python_callable", "ref": "my_package.tasks:fetch", "args": [], "kwargs": {"source": "api"}, "timeout": null},
      "name": "fetch",
      "description": null,
      "retries": 1,
      "on_success": null,
      "on_failure": null
    }
  ],
  "edges": [
    {"source": "fetch", "target": "transform", "condition": null, "name": null, "description": null}
  ]
}
```

`Job.to_dict()` additionally carries `job_id`, `status`, `trigger`, `executor_alias`, `jobstore_alias`, `misfire_grace_time`, `coalesce`, `max_instances` and `next_run_time`. String references are stored verbatim and never resolved on deserialization.

## Misfires and concurrency control

Three job parameters control what happens when a run is late:

```python
scheduler.add_job(
    workflow,
    trigger=IntervalTrigger(seconds=30),
    job_id="my_job",
    misfire_grace_time=60,   # max tolerated lateness in seconds; beyond it, publish job.missed and skip
    coalesce=True,           # True: merge missed runs into one; False: run each missed time
    max_instances=1,         # max concurrent instances; beyond it, publish job.max_instances
)
```

Set global defaults with `Scheduler(job_defaults={...})`.

## Web API

### Startup

```python
from fastapi import FastAPI

from schedflow.api.rest import create_app
from schedflow.core import Scheduler

scheduler = Scheduler()
app = create_app(scheduler, title="Scheduler API")

# Or mount onto an existing app
from schedflow.api.rest import mount_routes
mount_routes(app, scheduler)
```

Every endpoint returns `{"code": 0, "data": ..., "message": "ok"}`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/jobs` | Create a job (`workflow` + `trigger` JSON) |
| GET | `/api/jobs` | List jobs |
| GET | `/api/jobs/{job_id}` | Get one job |
| PUT | `/api/jobs/{job_id}` | Update a job |
| DELETE | `/api/jobs/{job_id}` | Delete a job |
| POST | `/api/jobs/{job_id}/pause` | Pause a job |
| POST | `/api/jobs/{job_id}/resume` | Resume a job |
| POST | `/api/jobs/{job_id}/run` | Run once immediately |
| POST | `/api/jobs/{job_id}/reschedule` | Reschedule (body: `{"trigger": {...}}`) |
| GET | `/api/jobs/{job_id}/logs` | List execution logs |
| GET | `/api/jobs/{job_id}/logs/{log_id}` | One log in detail |
| GET | `/api/scheduler/status` | Scheduler status (state/state_name/job_count) |
| POST | `/api/scheduler/start` | Start the scheduler |
| POST | `/api/scheduler/pause` | Pause the scheduler |
| POST | `/api/scheduler/resume` | Resume the scheduler |
| POST | `/api/scheduler/shutdown` | Shut down the scheduler |

### Create-job example

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": {
      "flow_id": "etl",
      "nodes": [
        {"node_id": "fetch", "task": {"ref": "my_package.tasks:fetch", "kwargs": {"source": "api"}}},
        {"node_id": "process", "task": "my_package.tasks:process"}
      ],
      "edges": [{"source": "fetch", "target": "process"}]
    },
    "trigger": {"type": "interval", "args": {"seconds": 60}},
    "job_id": "etl_job",
    "name": "data pipeline"
  }'
```

Notes:

- `task` may be a plain string, equivalent to `{"type": "python_callable", "ref": "..."}`;
- `trigger.args` matches the trigger constructor (e.g. `interval` accepts `weeks/days/hours/minutes/seconds/start_date/end_date/timezone/jitter`);
- cycles or edges to unknown nodes return **422**; duplicate `job_id` returns **409**; unknown `job_id` returns **404**. `JobNotFoundError`/`JobConflictError` are mapped to the right HTTP status automatically.

### Authentication

The Web API has no auth by default. To protect it, attach middleware to the FastAPI app manually (built-in `JWTBackend`/`APIKeyBackend` live in `schedflow.auth.security`, or implement a custom `AuthBackend`):

```python
from schedflow.api.middleware import AuthMiddleware
from schedflow.auth.security import APIKeyBackend

# APIKeyBackend validates the X-API-Key header against API key records
# stored in the metadata database
app.add_middleware(AuthMiddleware, backends=[APIKeyBackend()])
```

```python
from schedflow.auth.security import AuthBackend, AuthResult


class MyAuth(AuthBackend):
    async def authenticate(self, request) -> AuthResult:
        token = request.headers.get("Authorization")
        ok = token == "Bearer my-token"
        return AuthResult(success=ok, user_id="u1", method="custom")


app.add_middleware(AuthMiddleware, backends=[MyAuth()])
```

!!! note
    `AuthResult` has `success` / `user_id` / `method` fields. Before using the built-in `APIKeyBackend`, configure an API key record in the metadata database (the backend validates the `X-API-Key` request header).

### Real-time updates

The Web API does not currently ship an SSE route. A frontend can poll `GET /api/jobs/{job_id}/logs` or implement push from the SDK events.

## Custom components

Custom components are implemented by **subclassing the public base classes** and injecting instances directly — no entry points required:

### Custom trigger

```python
from datetime import datetime, timedelta

from pydantic import BaseModel

from schedflow.triggers.base import BaseTrigger, Trigger


class BusinessHoursTriggerModel(BaseModel):
    """Internal validation model: triggers still use a Pydantic model as the serialization contract."""

    interval_minutes: int = 30


class BusinessHoursTrigger(BaseTrigger):
    """Fires every N minutes during business hours (Mon-Fri 9:00-17:00)."""

    _trigger_type = "business_hours"    # auto-registers the type for from_dict()
    _pydantic_model_cls = BusinessHoursTriggerModel

    def __init__(self, *, interval_minutes: int = 30):
        super().__init__(None, interval_minutes=interval_minutes)
        self.interval = timedelta(minutes=interval_minutes)

    def get_next_fire_time(self, previous_fire_time, now):
        next_time = (previous_fire_time or now) + self.interval
        if next_time.weekday() >= 5:
            next_time += timedelta(days=7 - next_time.weekday())
        if next_time.hour < 9:
            next_time = next_time.replace(hour=9, minute=0, second=0)
        elif next_time.hour >= 17:
            next_time = next_time.replace(hour=9, minute=0, second=0) + timedelta(days=1)
        return next_time.astimezone()   # keep the timezone (the scheduler compares with an aware now)


scheduler.add_job(workflow, trigger=BusinessHoursTrigger(interval_minutes=15))
```

!!! note
    Triggers expose explicit keyword constructors but still use a Pydantic model internally as the serialization contract, so a custom trigger must provide both `_trigger_type` and `_pydantic_model_cls`. Setting `_trigger_type` makes `Trigger.from_dict()` recognize the type automatically.

### Custom job store

Subclass `schedflow.core.jobstore.JobStore` and implement `add / update / remove / get / get_due / get_all / get_next_run_time / add_log / get_logs / get_log / close`:

```python
from schedflow.core.jobstore import JobStore


class MyJobStore(JobStore):
    def add(self, job): ...
    def update(self, job): ...
    def remove(self, job_id): ...
    def get(self, job_id): ...
    def get_due(self, now): ...
    def get_all(self): ...
    def get_next_run_time(self): ...
    def add_log(self, job_id, log): ...
    def get_logs(self, job_id): ...
    def get_log(self, job_id, log_id): ...
    def close(self): ...


scheduler = Scheduler(jobstore=MyJobStore())
```

### Custom executor

Subclass `schedflow.core.executor.Executor` and implement `submit(job, run_time)`:

```python
from schedflow.core.executor import Executor


class MyExecutor(Executor):
    def submit(self, job, run_time):
        log = job.run()
        self._scheduler._on_job_finished(job, run_time, log)


scheduler = Scheduler(executor=MyExecutor())
```

### Custom task runner

Task types are dispatched through `RunnerRegistry` (`TaskSpec.type` → `BaseRunner` instance). You can replace the implementation for a built-in type; `Workflow.add_task(type=...)` currently accepts only the four built-in types, so adding a brand-new type also requires extending `TaskSpec`'s type validation:

```python
from schedflow.core.result import TaskResult
from schedflow.runners.base import BaseRunner
from schedflow.runners.registry import RunnerRegistry


class MyRunner(BaseRunner):
    """Example: replace the built-in bash runner with a custom implementation."""

    def run(self, spec, *, context=None, **kwargs) -> TaskResult:
        return TaskResult(succeeded=True, result=spec.command.upper())


RunnerRegistry.register("bash", MyRunner())
```

!!! note
    `TaskSpec` accepts only the four `type` values `python_callable` / `python` / `python_script` / `bash`; registering a completely new task type also requires extending `TaskSpec`'s validation (not an open extension point in the current version).

!!! note "Entry points"
    Entry-point plugin registration has been removed. Executors and jobstores
    are registered in the static registry
    `schedflow.core.plugins` (`EXECUTOR_PLUGINS` / `JOBSTORE_PLUGINS`),
    and triggers in `schedflow.triggers.registry.TRIGGER_PLUGINS`; the
    configuration API (`/api/v1/components`) reads these registries directly.

## Advanced event subscription

Event callbacks receive a `SchedulerEvent` whose payload depends on the event kind:

```python
def on_job_missed(event):
    print(f"job {event.job_id} missed run time {event.run_time}")


def on_task_error(event):
    # task.* events carry the node's TaskRecord
    record = event.record
    print(f"node {record.node_id} failed: {record.error}")


scheduler.on("job.missed", on_job_missed)
scheduler.on("task.error", on_task_error)
scheduler.on("*", lambda event: print("any event:", event.kind))
```

!!! note "Task events vs job events"
    `task.*` events are published per node after the scheduler executes a job (`event.record` is the node's `TaskRecord`); the `job.succeeded` / `job.failed` job-level event follows. Subscribing only to `job.*` still gives you the same per-node state via `event.log.records`. Calling `Workflow.run()` directly publishes no events.
