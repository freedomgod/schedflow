# SchedFlow

<div align="center" markdown>

**Running scheduled tasks in Directed Acyclic Graph Mode**

[![PyPI](https://img.shields.io/pypi/v/schedflow)](https://pypi.org/project/schedflow/)
[![Python](https://img.shields.io/pypi/pyversions/schedflow)](https://pypi.org/project/schedflow/)
[![License](https://img.shields.io/github/license/freedomgod/schedflow)](https://github.com/freedomgod/schedflow/blob/main/LICENSE.txt)

</div>

SchedFlow is a lightweight **DAG workflow scheduling framework**: a "job" is no longer a single function call but a directed acyclic graph of task nodes and dependency edges. You can define complex pipelines with dependencies, conditional branching, and parallel execution — all with built-in triggers (cron/interval/date), multiple executors and job stores, and a REST API.

!!! note "Interface notes"
    The underlying interfaces use **explicit signatures** (IDE-friendly); you never need to know about Pydantic validation models. New code imports from `schedflow.core`, `schedflow.triggers`, and `schedflow.api.rest`.

## Key Features

| Category | Features |
|----------|----------|
| **DAG workflows** | `Workflow` defines nodes and dependency edges: topological execution, same-generation parallelism, conditional edges, cycle detection |
| **Task types** | Python callables / `"module:function"` string refs, `.py` script files, inline snippets, shell commands |
| **Explicit API** | Every public method uses explicit keyword signatures; pass callables directly, string refs resolve lazily at run time |
| **Triggers** | `DateTrigger` / `IntervalTrigger` / `CronTrigger` / `CalendarIntervalTrigger` / `AndTrigger` / `OrTrigger` with unified `to_dict()/from_dict()` |
| **Persistence** | `MemoryJobStore` / `SQLAlchemyJobStore` / `RedisJobStore` / `MongoDBJobStore`, unified JSON serialization, refs never resolved on load |
| **Executors** | `ThreadPoolExecutor` / `ProcessPoolExecutor` (JSON worker protocol, Windows-ready) / `DebugExecutor` |
| **Execution logs** | `ExecutionLog` records per-node status, result, error, timing and a DAG snapshot |
| **Web API** | Structured FastAPI REST API (`/api`) with a unified `{"code": 0, "data": ..., "message": "ok"}` response |
| **Dashboard** | Vue 3 + Element Plus UI: DAG editor, job management, execution logs, dark/light themes |

## Quick Example

A complete, copy-paste runnable example: it mixes several task types and can run either directly or through a scheduler every 60 seconds.

```python
from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


# Task function 1: a plain Python function
def fetch(source: str) -> str:
    return f"data from {source}"


# Task function 2: receives the upstream result via the _pre_results argument
def process(_pre_results) -> str:
    # _pre_results is a {"upstream node id": return value} dict,
    # here it is {"fetch": "data from api"}
    return _pre_results["fetch"].upper()


# Edge condition callback: receives the upstream TaskRecord and must return
# True for the downstream node to run
def should_report(record) -> bool:
    return record.status == "succeeded" and bool(record.result)


# 1. Define the workflow, mixing several task types
wf = Workflow("etl")

# Task type 1: a Python function (python_callable, the default)
wf.add_task("fetch", func=fetch, kwargs={"source": "api"}, retries=2)
# Task type 2: same, but func may also be a "module:function" string,
# resolved only at execution time
wf.add_task("process", func=process)   # e.g. func="my_module:process"
# Task type 3: a shell command (bash, run in a subprocess)
wf.add_task("report", type="bash", command="echo report generated")
# Task type 4: inline Python code (python_script, run via python -c)
wf.add_task("summary", type="python_script", script="print('summary ok')")

wf.add_edge("fetch", "process")
wf.add_edge("process", "report", condition=should_report)  # conditional edge
wf.add_edge("process", "summary")

# 2. Run once directly, without a scheduler
log = wf.run(max_workers=3)
print(log.succeeded, log.records["process"].result)  # True DATA FROM API

# 3. Hand it to a scheduler that fires every 60 seconds
scheduler = Scheduler()
scheduler.on("job.succeeded", lambda e: print(f"job {e.job_id} succeeded"))  # event subscription
scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),
    job_id="etl_job",
    misfire_grace_time=30,   # max tolerated lateness; beyond it, job.missed is published
    max_instances=2,         # max concurrent instances for this job
)
scheduler.start()

# The scheduler main loop runs in a background daemon thread: the main thread
# must stay alive, otherwise the process exits and the job never fires.
# Press Ctrl+C to stop cleanly:
try:
    import time

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
    print("Scheduler stopped.")
```

!!! tip "Want the full API tour?"
    The example above shows DAG definition, several task types (`python_callable` / `bash` / `python_script`; the fourth type, `python` script files, is covered below), `_pre_results` result passing, conditional edges, retries and scheduler events. The step-by-step walkthrough lives in the [Quickstart](quickstart.md), and the complete `Workflow` guide is in [DAG Workflows](user-guide/dag-workflow.md).

## Where to go next

- **[Introduction](introduction.md)** — motivation and architecture
- **[Installation](installation.md)** — install with the right extras
- **[Quickstart](quickstart.md)** — your first workflow in 5 minutes
- **[User Guide](user-guide/core-features.md)** — scheduler, triggers, stores, executors
- **[API Reference](api-reference/index.md)** — full API documentation

!!! tip "Language switch"
    This site defaults to Chinese (at the site root); the English version lives at `/en/`. Use the language dropdown in the top-right corner to switch.
