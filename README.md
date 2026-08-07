# SchedFlow

> **Documentation**: [https://schedflow.readthedocs.io/](https://schedflow.readthedocs.io/)

**A lightweight scheduled-task framework that runs each job as a Directed Acyclic Graph (DAG) workflow.**

[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE.txt)
[![PyPI](https://img.shields.io/badge/pypi-schedflow-orange)](https://pypi.org/project/schedflow/)
[![Documentation](https://img.shields.io/badge/docs-readthedocs-brightgreen)](https://schedflow.readthedocs.io/)

SchedFlow upgrades the classic *"one job = one function call"* model into *"one job = one DAG workflow"*: task nodes with dependency edges, conditional branching, parallel execution, per-node retries and callbacks, structured execution logs, persistence, a REST API and a web dashboard.

New code imports from `schedflow.core`, `schedflow.triggers` and `schedflow.api.rest`.

## Key features

| Category | Features |
|----------|----------|
| **DAG workflows** | `Workflow`: nodes (`add_task`) + dependency edges (`add_edge`) with cycle detection, topological execution and same-layer parallelism |
| **Task types** | `python_callable` (a callable or `"module:function"` string), `python` (`.py` script), `python_script` (inline code), `bash` (shell command) |
| **Explicit API** | Explicit keyword signatures; string references are resolved lazily at execution time |
| **Triggers** | `DateTrigger`, `IntervalTrigger`, `CronTrigger`, `CalendarIntervalTrigger`, `AndTrigger`, `OrTrigger`; unified `to_dict()/from_dict()` |
| **Persistence** | `MemoryJobStore`, `SQLAlchemyJobStore`, `RedisJobStore`, `MongoDBJobStore`; JSON-only serialization, references never resolved on load |
| **Executors** | `ThreadPoolExecutor`, `ProcessPoolExecutor` (JSON worker protocol, Windows-ready), `DebugExecutor` |
| **Execution logs** | `ExecutionLog` / `TaskRecord`: per-node status, result, error, timing, stdout/stderr and a DAG snapshot |
| **Web API** | FastAPI REST API under `/api` with a unified `{"code": 0, "data": ..., "message": "ok"}` response |
| **Dashboard** | Vue 3 + Element Plus UI: DAG editor, job management, execution logs, dark/light themes |

## Quick start

A complete, runnable example that mixes several task types and shows both direct execution and 60-second scheduling:

```python
from schedflow.core import Scheduler, Workflow
from schedflow.triggers import IntervalTrigger


def fetch(source: str) -> str:
    return f"data from {source}"


def process(_pre_results) -> str:
    # _pre_results = {"fetch": "data from api"} — results of upstream nodes
    return _pre_results["fetch"].upper()


def should_report(record) -> bool:
    return record.status == "succeeded" and bool(record.result)


wf = Workflow("etl")
# Task type 1: a Python function (python_callable, the default)
wf.add_task("fetch", func=fetch, kwargs={"source": "api"}, retries=2)
# Task type 2: func may also be a "module:function" string reference
wf.add_task("process", func=process)
# Task type 3: a shell command (bash)
wf.add_task("report", type="bash", command="echo report generated")
# Task type 4: inline Python code (python_script)
wf.add_task("summary", type="python_script", script="print('summary ok')")

wf.add_edge("fetch", "process")
wf.add_edge("process", "report", condition=should_report)  # conditional edge
wf.add_edge("process", "summary")

# Run once without a scheduler
log = wf.run(max_workers=3)
print(log.succeeded, log.records["process"].result)   # True DATA FROM API

# Schedule it: run every 60 seconds
scheduler = Scheduler()
scheduler.add_job(
    wf,
    trigger=IntervalTrigger(seconds=60),
    job_id="etl_job",
    misfire_grace_time=30,
    max_instances=2,
)
scheduler.start()

# The scheduler loop runs in a background daemon thread — keep the main
# thread alive, otherwise the process exits and the job never fires.
try:
    import time

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    scheduler.shutdown()
```

## Installation

Requires Python 3.11+.

```bash
pip install schedflow                  # core package
pip install schedflow[sqlalchemy]      # SQLAlchemy job store
pip install schedflow[redis]           # Redis job store
pip install schedflow[mongodb]         # MongoDB job store
pip install schedflow[web]             # FastAPI Web API
```

## Core concepts

- **Workflow** — a DAG. `add_task()` adds nodes, `add_edge()` adds (optionally conditional) dependency edges with built-in cycle detection; `run()` executes directly; `to_dict()/from_dict()` are the single JSON serialization path.
- **TaskSpec** — what a node executes. Four types: `python_callable`, `python`, `python_script`, `bash`.
- **Trigger** — when a job runs: `DateTrigger`, `IntervalTrigger`, `CronTrigger`, `CalendarIntervalTrigger`, `AndTrigger`/`OrTrigger`.
- **Job** — a workflow bound to a trigger plus scheduling metadata (misfire grace, coalescing, max instances).
- **Scheduler** — the main loop. Add/update/pause/resume/remove jobs, run jobs immediately, persist and query execution logs, subscribe to events.
- **JobStore** — persistence for jobs and logs: `MemoryJobStore`, `SQLAlchemyJobStore`, `RedisJobStore`, `MongoDBJobStore`.
- **Executor** — how a job runs: `ThreadPoolExecutor`, `ProcessPoolExecutor`, `DebugExecutor`.
- **ExecutionLog / TaskRecord** — per-run, per-node status, results, errors, timing and captured output.

## Web API (FastAPI)

```python
from schedflow.api.rest import create_app
from schedflow.core import Scheduler

app = create_app(Scheduler(), title="Scheduler API")
# uvicorn my_module:app
```

Key endpoints (all under `/api`): job CRUD plus `pause` / `resume` / `run` / `reschedule`, job logs, and scheduler `status` / `start` / `pause` / `resume` / `shutdown`. Every response uses `{"code": 0, "data": ..., "message": "ok"}`.

## Running the web dashboard

Both CLI commands default to **production mode**; development behaviour is
only enabled when `--dev` is passed explicitly:

```bash
uv run schedflow-backend        # production: no reload watcher, INFO logs (default)
uv run schedflow-backend --dev  # development: hot reload + DEBUG logs

uv run schedflow-frontend        # production: build (as needed) then vite preview (default)
uv run schedflow-frontend --dev  # development: Vite dev server with HMR
```

Production mode does not watch the filesystem, so runtime writes such as
`jobs.db` no longer produce noisy "changes detected" output or risk leaving
multiple scheduler processes behind. In development mode, `jobs.db`, `.git`
and other noisy paths are excluded from the reload watcher.

## Development

```bash
python -m pytest          # run the test suite
ruff check .              # lint
```

Runnable examples live in [`examples/`](examples/README.md).

## License

MIT — see [LICENSE.txt](LICENSE.txt).
