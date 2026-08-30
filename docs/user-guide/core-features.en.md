# Core Features

## Scheduler

The scheduler is the central component that manages job execution: it runs a main loop that pulls due jobs from the job store, computes next run times, hands jobs to the executor, publishes events and persists execution logs.

The framework provides **one unified `Scheduler` class** (`schedflow.core.Scheduler`); you choose the job store, executor and timezone via constructor arguments:

```python
from schedflow.core import Scheduler

scheduler = Scheduler(
    timezone="Asia/Shanghai",          # optional; defaults to the local timezone
    project_root="./my_project",       # optional; base for relative string refs
)
```

!!! note "Choosing a scheduler"
    Use `schedflow.core.Scheduler`; its `start()` runs the main loop in a background thread. For blocking foreground runs, `join()` the thread or wait on an event yourself.

### Lifecycle

```python
scheduler.start(paused=False)   # start the main loop; paused=True defers job processing
scheduler.pause()               # pause job processing (running jobs are not interrupted)
scheduler.resume()              # resume job processing
scheduler.shutdown(wait=True)   # stop; wait=True waits for running jobs to finish
```

## Triggers

Triggers decide **when** a job runs. Every trigger uses explicit keyword construction and unified `to_dict()/from_dict()` serialization:

```python
from schedflow.triggers import (
    AndTrigger,
    CalendarIntervalTrigger,
    CronTrigger,
    DateTrigger,
    IntervalTrigger,
    OrTrigger,
)
```

### DateTrigger

Runs once at the given date/time:

```python
trigger = DateTrigger(run_date="2026-08-01 10:00:00")
trigger = DateTrigger(datetime(2026, 8, 1, 10, 0))       # datetime objects work too
```

### IntervalTrigger

Repeats at a fixed interval:

```python
IntervalTrigger(seconds=30)
IntervalTrigger(minutes=5, hours=1)
IntervalTrigger(days=1, start_date="2026-01-01", end_date="2026-12-31")
IntervalTrigger(seconds=60, jitter=5)          # jitter: random delay of at most 5s
```

### CronTrigger

Schedules with cron-style expressions:

```python
# Daily at 03:00
CronTrigger(hour=3)

# Every Monday at noon
CronTrigger(day_of_week="mon", hour=12)

# Every 15 minutes on weekdays
CronTrigger(minute="*/15", day_of_week="mon-fri")

# First day of every month at midnight
CronTrigger(day=1, hour=0)

# From a standard 5-field crontab expression
CronTrigger.from_crontab("0 9 * * 1-5", timezone="Asia/Shanghai")
```

### CalendarIntervalTrigger

Runs at calendar-aligned intervals, always at the same wall-clock time:

```python
CalendarIntervalTrigger(months=1, hour=9, minute=0)   # same day every month at 09:00
CalendarIntervalTrigger(days=7, hour=18, minute=30)   # every 7 days at 18:30
```

!!! warning
    With `months`/`years`, avoid start dates near the end of the month (29th–31st) and leap days, or some months will be skipped.

### Combining triggers (AND / OR)

```python
# Fires only at times all sub-triggers agree on (intersection)
AndTrigger(triggers=[CronTrigger(hour=9), IntervalTrigger(seconds=30)])

# Fires when any sub-trigger fires (union)
OrTrigger(triggers=[DateTrigger(run_date="2026-01-01"), CronTrigger(day_of_week="fri")])
```

!!! warning
    `AndTrigger` should only combine "fixed-time" triggers (e.g. Cron/CalendarInterval); combining it with `IntervalTrigger` can make the scheduler search for an intersection for a very long time.

### Trigger serialization

```python
from schedflow.triggers.base import Trigger

data = trigger.to_dict()        # {"type": "interval", "args": {"seconds": 60, ...}}
trigger = Trigger.from_dict(data)   # rebuild from JSON (Trigger is an alias of BaseTrigger)
```

This is also the JSON contract used by the Web API's `{"trigger": {"type": ..., "args": {...}}}`.

## Job Stores

Job stores persist job definitions and execution logs. `JobStore` is an explicit interface; every implementation uses **JSON serialization** (no pickle) and **never resolves string references on load** — jobs are not silently dropped when a target module is temporarily unavailable.

| Store | Use case | Install |
|-------|----------|--------|
| `MemoryJobStore` | In-memory (volatile), dev/test | built-in |
| `SQLAlchemyJobStore` | SQLite / PostgreSQL / MySQL ... | `[sqlalchemy]` |
| `RedisJobStore` | Redis | `[redis]` |
| `MongoDBJobStore` | MongoDB | `[mongodb]` |

```python
from schedflow.core import Scheduler
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

store = SQLAlchemyJobStore(url="sqlite:///data/jobs.db")
scheduler = Scheduler(jobstore=store)
```

The unified store interface:

```python
store.add(job)                  # insert (duplicate id raises JobConflictError)
store.update(job)               # update (missing job raises JobNotFoundError)
store.remove(job_id)            # delete
store.get(job_id)               # fetch one
store.get_all()                 # all jobs (scheduled first, paused last)
store.get_due(now)              # due jobs sorted by next_run_time
store.get_next_run_time()       # earliest pending run time
store.add_log(job_id, log)      # persist an execution log
store.get_logs(job_id)          # list logs
store.get_log(job_id, log_id)   # fetch one log
store.close()                   # release underlying connections
```

## Executors

Executors decide **how** a job runs:

| Executor | Concurrency model | Best for |
|----------|-------------------|----------|
| `ThreadPoolExecutor` | Thread pool (10 threads by default) | IO-bound tasks |
| `ProcessPoolExecutor` | Process pool (JSON worker protocol) | CPU-bound tasks; Windows-ready |
| `DebugExecutor` | Synchronous, in the calling thread | Development/tests |

```python
from schedflow.core import Scheduler
from schedflow.core.executor import ProcessPoolExecutor, ThreadPoolExecutor

scheduler = Scheduler(
    executor=ProcessPoolExecutor(max_workers=4),
)
```

### Process pool notes

`ProcessPoolExecutor` sends only `Job.to_dict()` (pure JSON) to child processes, which rebuild and run the job, so it works on Windows (spawn). The trade-off: nodes must use **string references** (importable `"module:function"` or script paths) — closures and lambdas are not supported.

## Job management

### Add a job

```python
job = scheduler.add_job(
    workflow,                                   # Workflow instance or its JSON dict
    trigger=IntervalTrigger(seconds=30),        # optional; None means manual runs only
    job_id="my_job",                            # optional; auto-generated if omitted
    name="My job",
    description="example job",
    misfire_grace_time=60,                      # max tolerated lateness in seconds
    coalesce=True,                              # merge multiple missed runs into one
    max_instances=1,                            # max concurrent instances
    replace=False,                              # replace an existing job with the same id
)
```

!!! note "flow_id vs job_id"
    The `flow_id` in `Workflow("etl")` identifies the **workflow definition** (it ends up in `log.flow_id` and does not need to be unique). The `job_id` passed to `add_job(..., job_id=...)` is the **unique key of the scheduled job** in the job store (a UUID is generated when omitted) and is used for job queries/updates/removal, `event.job_id` and log lookups. The two are not bound to each other: the same workflow can be registered under several different `job_id`s, and a direct `Workflow.run()` has no job, so `log.job_id` is `None`.

### Query / update / remove

```python
job = scheduler.get_job("my_job")
jobs = scheduler.get_jobs()

scheduler.update_job("my_job", name="New name", trigger=CronTrigger(hour=3))
scheduler.remove_job("my_job")
```

### Pause / resume / reschedule / run now

```python
scheduler.pause_job("my_job")
scheduler.resume_job("my_job")
scheduler.reschedule_job("my_job", CronTrigger(hour=3))

log = scheduler.run_job_now("my_job")     # run once immediately, ignoring the trigger
```

### Execution logs

```python
logs = scheduler.get_job_logs("my_job")              # all logs for this job
log = scheduler.get_job_log("my_job", log_id)        # one log in detail
```

## Events

The event system follows a **publish/subscribe (pub/sub)** model: the scheduler publishes events at key points and your application responds by subscribing callbacks. Every callback has the signature `callback(event: SchedulerEvent) -> None`.

### Quick start

```python
def on_job_succeeded(event):
    print(f"job {event.job_id} succeeded")
    for node_id, record in event.log.records.items():
        print(f"  {node_id}: {record.status} result={record.result}")


scheduler = Scheduler()
scheduler.on("job.succeeded", on_job_succeeded)   # subscribe
# scheduler.off("job.succeeded", on_job_succeeded)  # unsubscribe (optional)
```

- `scheduler.on(kind, callback)` registers the callback on **that scheduler instance's** event bus; `scheduler.off(kind, callback)` unsubscribes it;
- when an event fires, the callback receives a `SchedulerEvent` object (attributes below);
- multiple callbacks may be registered for the same kind and run in registration order; an exception in one callback does not affect the others;
- subscribing to `"*"` receives **every** event published by that scheduler.

### What is EventBus?

`EventBus` is a thread-safe **publish/subscribe container**: `subscribe()` registers a callback, `unsubscribe()` removes one, and `publish()` fires an event.

```python
from schedflow.core import EventBus

bus = EventBus()
bus.subscribe("job.failed", my_callback)
```

!!! warning "EventBus is not a global broadcast"
    `bus.subscribe("job.failed", callback)` only registers the callback on **that EventBus instance**. Subscribers receive events only when a scheduler (or any other code) calls `publish()` on the **same instance**; it neither listens to nor receives events published on other buses.

Every `Scheduler` creates its own `EventBus` as its internal bus (`scheduler._events`); `scheduler.on(...)` is equivalent to subscribing on its own bus:

```python
scheduler = Scheduler()
scheduler.on("job.failed", cb)                    # subscribe to this scheduler
scheduler._events.subscribe("job.failed", cb)     # equivalent (internal bus)
```

Therefore:

- **Two different `Scheduler` instances have independent buses and never share events** — `bus.subscribe(...)` will not receive events published by another scheduler;
- a standalone `EventBus()` receives nothing from schedulers unless you call `bus.publish(...)` yourself (useful for in-process decoupled notifications or custom event forwarding).

### Event kinds and when they fire

The table below lists every event kind, **when it fires**, and which attributes (other than `event.kind`) are **available in the callback** — any attribute not listed is `None`:

| Event kind | When it fires | Attributes available in the callback |
|------------|---------------|-------------------------------------|
| `scheduler.started` | `start()` succeeded | none (only `event.kind`) |
| `scheduler.paused` | scheduler paused | none (only `event.kind`) |
| `scheduler.resumed` | scheduler resumed | none (only `event.kind`) |
| `scheduler.shutdown` | scheduler shut down | none (only `event.kind`) |
| `job.added` | `add_job()` succeeded | `job_id` |
| `job.updated` | `update_job()` succeeded | `job_id` |
| `job.removed` | `remove_job()`, or a one-shot job removed after running | `job_id` |
| `job.paused` | job paused | `job_id` |
| `job.resumed` | job resumed | `job_id` |
| `job.started` | job execution begins | `job_id`, `run_time` |
| `job.succeeded` | ran with no `failed` node | `job_id`, `run_time`, `log` |
| `job.failed` | ran with at least one `failed` node | `job_id`, `run_time`, `log` |
| `job.missed` | run skipped because `misfire_grace_time` was exceeded | `job_id`, `run_time` |
| `job.max_instances` | run rejected because `max_instances` was reached | `job_id`, `run_time` |
| `task.executed` | after a job run, for each `succeeded` node | `job_id`, `run_time`, `log`, `record` |
| `task.error` | after a job run, for each `failed` node | `job_id`, `run_time`, `log`, `record` |
| `task.skipped` | after a job run, for each `skipped` node | `job_id`, `run_time`, `log`, `record` |

- `run_time` is the scheduled run time for scheduled runs and `None` for manual `run_job_now()`;
- the full list of valid kinds is `schedflow.core.events.EVENT_KINDS`.

!!! note "Where `task.*` events are published"
    `task.*` events are published per node **after the scheduler executes a job** — both for scheduled runs and `run_job_now()`. In the callback, `event.record` is the node's `TaskRecord` and `event.log` is the run's `ExecutionLog`. Calling `Workflow.run()` directly (without a scheduler) publishes no events; read the returned `ExecutionLog` instead.

### What each SchedulerEvent attribute is

The `SchedulerEvent` received by callbacks always has 5 attributes. Apart from `kind`, any attribute that is not populated is `None`:

| Attribute | Type | Populated when | What it is |
|-----------|------|----------------|------------|
| `event.kind` | `str` | always | the event kind string, e.g. `"job.succeeded"`, `"task.error"` |
| `event.job_id` | `str` | `job.*` and `task.*` events | the unique key of the related scheduled job (matches `add_job(job_id=...)`) |
| `event.run_time` | `datetime` | scheduled runs | the scheduled run time; `None` for manual `run_job_now()` |
| `event.log` | `ExecutionLog` | `job.succeeded` / `job.failed` and `task.*` | the **full execution-log object** of this run, see below |
| `event.record` | `TaskRecord` | `task.*` events only | the **execution-record object** of the related node, see below |

#### event.log — ExecutionLog: the full log of one run

`event.log` is an **`ExecutionLog`** object (`schedflow.core.log.ExecutionLog`) describing the **complete result of one workflow run**:

| Field / method | Type | Meaning |
|----------------|------|---------|
| `log.log_id` | `str` | unique log ID for this run (like `flowlog_xxx`) |
| `log.flow_id` | `str \| None` | the workflow's `flow_id` |
| `log.job_id` | `str \| None` | the owning job ID (`None` for a direct `Workflow.run()`) |
| `log.start_time` / `log.end_time` | `datetime` | start and end time |
| `log.duration` | `float \| None` | total duration in seconds |
| `log.records` | `dict[str, TaskRecord]` | a `node_id -> TaskRecord` dict for every node |
| `log.dag_snapshot` | `dict \| None` | JSON snapshot of the DAG structure at execution time |
| `log.succeeded` | `bool` | whether no node `failed` |
| `log.failed_nodes()` | `list[TaskRecord]` | records of all failed nodes |
| `log.skipped_nodes()` | `list[TaskRecord]` | records of all skipped nodes |

```python
def on_job_finished(event):
    log = event.log                 # an ExecutionLog object
    print(f"{log.log_id} flow={log.flow_id} job={log.job_id} "
          f"duration={log.duration}s succeeded={log.succeeded}")
    for node_id, record in log.records.items():
        print(f"  {node_id}: {record.status} result={record.result} error={record.error}")
```

#### event.record — TaskRecord: one node's execution record

`event.record` is a **`TaskRecord`** object (`schedflow.core.log.TaskRecord`) describing **one node** in that run:

| Field | Type | Meaning |
|-------|------|---------|
| `record.node_id` | `str` | node ID |
| `record.task_id` | `str \| None` | task ID |
| `record.status` | `str` | `pending` / `running` / `succeeded` / `failed` / `skipped` |
| `record.result` | `Any` | the node's return value (`None` for subprocess-style tasks; output goes to `stdout`) |
| `record.error` | `str \| None` | the failure reason |
| `record.skip_reason` | `str \| None` | why the node was skipped |
| `record.stdout` / `record.stderr` | `str \| None` | captured output for subprocess-style tasks |
| `record.exit_code` | `int \| None` | exit code for subprocess-style tasks |
| `record.start_time` / `record.end_time` | `datetime` | node start and end time |
| `record.duration` | `float \| None` | node duration in seconds |

```python
def on_task_event(event):
    r = event.record                # a TaskRecord object
    print(f"{event.job_id}/{r.node_id}: {r.status}")
    if r.error:
        print(f"  error: {r.error}")
    if r.skip_reason:
        print(f"  skip reason: {r.skip_reason}")
```

### Full example: monitor one job run

```python
def monitor(event):
    if event.kind in ("task.executed", "task.error", "task.skipped"):
        r = event.record
        print(f"[task] {event.job_id}/{r.node_id} -> {r.status}")
        if r.error:
            print(f"       error: {r.error}")
    elif event.kind in ("job.succeeded", "job.failed"):
        log = event.log
        print(f"[job] {event.job_id} {event.kind} took {log.duration:.2f}s")


scheduler.on("*", monitor)
```

You can also use the `EventBus` directly:

```python
from schedflow.core import EventBus

bus = EventBus()
bus.subscribe("job.failed", callback)
bus.unsubscribe("job.failed", callback)
```

## Configuration

### Timezone

The scheduler defaults to the local timezone; pass `timezone` explicitly to override:

```python
from datetime import timezone

Scheduler(timezone="Asia/Shanghai")
Scheduler(timezone=timezone.utc)
```

### Job defaults

```python
scheduler = Scheduler(job_defaults={
    "misfire_grace_time": 30,
    "coalesce": True,
    "max_instances": 2,
})
```

### Project root

`project_root` is the base directory for relative path string references:

```python
Scheduler(project_root="/data/projects/my_app")
```

When a workflow does not set its own `project_root`, it inherits the scheduler's value.

### Metadata database and .env

The bundled management metadata (users, API keys, theme, variables) is read from environment variables or a `.env` file via `schedflow.configs.settings.Settings`:

```ini
# .env
APP_ENV=production
HOST=0.0.0.0
PORT=8000
SCHEDFLOW_META_DB=data/scheduler_meta.db
```

The shipped defaults are **production-safe** (`APP_ENV=production`,
`RELOAD=false`, `LOG_LEVEL=INFO`), and `schedflow-backend` /
`schedflow-frontend` start in production mode out of the box. Development
behaviour (hot reload, DEBUG logs, Vite HMR) is only enabled with explicit
flags:

```bash
uv run schedflow-backend --dev
uv run schedflow-frontend --dev
```

Production mode does not watch the filesystem, so runtime writes such as
`data/jobs.db` no longer produce "changes detected" output, and hot reload
cannot leave multiple scheduler processes behind.
