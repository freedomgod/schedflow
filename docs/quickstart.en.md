# Quickstart

This guide walks you through creating and running your first SchedFlow DAG workflow. Every snippet can be copied and run as-is.

## Prerequisites

Make sure SchedFlow is [installed](installation.md):

```bash
pip install schedflow
```

## Step 1: Define your task functions

Create a Python file (e.g. `my_workflow.py`) with the functions your workflow will execute:

```python
def fetch_data(**kwargs):
    """Simulate fetching data from an API."""
    print("Fetching data...")
    return {"temperature": 25.4, "humidity": 0.68}


def process_data(_pre_results=None, **kwargs):
    """Process the data; receives upstream results."""
    upstream = list(_pre_results.values())[0] if _pre_results else {}
    temp = upstream.get("temperature", 0)
    humidity = upstream.get("humidity", 0)
    return {"heat_index": temp * humidity * 100}


def alert(**kwargs):
    """Send an alert."""
    print("Alert! The workflow completed.")
    return "alert sent"
```

!!! tip "Function parameters"
    - Upstream return values are injected through the `_pre_results` keyword argument (a `node_id -> result` dict);
    - The framework filters arguments against the function signature, so extra kwargs never cause `TypeError`;
    - You can also pass `"module:function"` strings (e.g. `"my_workflow:fetch_data"`); they are resolved at execution time.

## Step 2: Build the DAG workflow

Use `Workflow` to define nodes and dependency edges:

```python
from schedflow.core import Workflow

wf = Workflow("data_pipeline")

# Add task nodes: fetch → process → alert
wf.add_task("fetch", func=fetch_data, name="Fetch")
wf.add_task("process", func=process_data, name="Process")
wf.add_task("alert", func=alert, name="Alert")

# Add dependency edges that define the execution order
wf.add_edge("fetch", "process")
wf.add_edge("process", "alert")
```

The first argument of `add_task()` is the node ID (unique within a workflow); `func` accepts a callable or a string reference. `add_edge(source, target)` declares a dependency and runs **cycle detection** — an edge that would create a cycle raises `CycleError` and is not added.

## Step 3: Run the workflow directly

Run it once without a scheduler:

```python
log = wf.run(max_workers=3)

print("succeeded:", log.succeeded)
for node_id, record in log.records.items():
    print(f"  {node_id}: {record.status} result={record.result}")
```

Execution model: nodes in the same topological generation run in parallel (`max_workers` caps the parallelism); generations run sequentially. The run returns an `ExecutionLog` whose `records` map node IDs to status, result, error and timing.

## Step 4: Schedule it with the Scheduler

```python
from schedflow.core import Scheduler
from schedflow.triggers import IntervalTrigger

scheduler = Scheduler()

scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),   # every 60 seconds
    job_id="data_pipeline_job",
    name="Data pipeline",
    max_instances=2,
    misfire_grace_time=30,
)

scheduler.start()

import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
    print("Scheduler stopped.")
```

!!! note "Why keep the process alive?"
    `Scheduler.start()` runs its main loop in a **background daemon thread** and returns immediately. If the main thread exits afterwards, the process ends and the scheduler stops with it — this is the most common reason a job never seems to fire. The `while True` loop above simply keeps the main thread alive; any other way of blocking it works too (waiting on an event, serving a web app, etc.).

All triggers use explicit keyword construction: `IntervalTrigger(seconds=60)`, `CronTrigger(hour=3, minute=0)`, `DateTrigger(run_date="2026-08-01 10:00:00")`, and more — see [Core Features](user-guide/core-features.md).

## Step 5: Add a conditional branch

Attach a condition to an edge; the downstream node runs only when the condition is met, otherwise it is marked `skipped`:

```python
def should_alert(record) -> bool:
    """Alert only when heat_index exceeds 1500."""
    return bool(record.result) and record.result.get("heat_index", 0) > 1500


wf.add_edge("process", "alert", condition=should_alert)

log = wf.run()
# heat_index = 25.4 * 0.68 * 100 = 1727 > 1500, so the condition holds and alert runs
print(log.records["alert"].status)          # succeeded
```

The condition receives the upstream `TaskRecord` and returns `True` to allow or `False` to skip. If an upstream node fails, downstream nodes are automatically marked `skipped` while unaffected parallel branches keep running.

## Step 6: Manage it over the Web API (optional)

The Web API mirrors the SDK one-to-one:

```python
from schedflow.api.rest import create_app
from schedflow.core import Scheduler

scheduler = Scheduler()
app = create_app(scheduler, title="Scheduler API")

# Run with: uvicorn my_module:app
```

The bundled CLI can also start the backend and the web dashboard directly.
Both commands **default to production mode**; only add `--dev` to switch to
the development environment:

```bash
uv run schedflow-backend         # production: no reload watcher, INFO logs (default)
uv run schedflow-backend --dev   # development: hot reload + DEBUG logs
uv run schedflow-frontend        # production: build (as needed) then vite preview (default)
uv run schedflow-frontend --dev  # development: Vite dev server with HMR
```

See the Web API section of [Advanced Usage](user-guide/advanced-usage.md) for the full endpoint list and request examples.

## Next steps

- Read **[Core Features](user-guide/core-features.md)** — triggers, job stores, executors and events
- Learn **[Advanced Usage](user-guide/advanced-usage.md)** — retries, timeouts, serialization and custom components
- Dive into **[DAG Workflows](user-guide/dag-workflow.md)** — the complete Workflow API
- Browse the **[API Reference](api-reference/index.md)**
