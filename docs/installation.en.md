# Installation

## Requirements

- **Python** 3.11 or newer
- **pip** (or [uv](https://docs.astral.sh/uv/), [pipx](https://pipx.pypa.io/))

## Base install

Install the core package with the default in-memory job store and thread-pool executor:

```bash
pip install schedflow
```

This gives you:

- The complete DAG workflow engine (`Workflow`, `TaskSpec`, `ExecutionLog`)
- All trigger types (`date`, `interval`, `cron`, `calendarinterval`, `and`, `or`)
- The in-memory job store (`MemoryJobStore`)
- Thread-pool and debug executors (`ThreadPoolExecutor`, `DebugExecutor`)
- The unified `Scheduler` and the Web API builder (`create_app`; FastAPI itself needs the `[web]` extra below)

## Optional dependencies

SchedFlow uses extras to keep dependencies minimal:

### Database job stores

```bash
# SQLAlchemy (SQLite, PostgreSQL, MySQL, ...)
pip install schedflow[sqlalchemy]

# MongoDB
pip install schedflow[mongodb]

# Redis
pip install schedflow[redis]
```

### Optional executors

```bash
# Gevent executor
pip install schedflow[gevent]

# Tornado executor
pip install schedflow[tornado]

# Twisted executor
pip install schedflow[twisted]
```

!!! note "About AsyncIO"
    The core scheduler ships two families of executors: the regular
    `ThreadPoolExecutor` / `ProcessPoolExecutor` / `DebugExecutor`
    (`core.executor`) and the async-flavored `AsyncIOExecutor` /
    `GeventExecutor` / `TornadoExecutor` / `TwistedExecutor`
    (`core.async_executors`), all implementing the unified `Executor` interface.

### Web API

```bash
pip install schedflow[web]
```

This installs FastAPI, Uvicorn and the authentication dependencies (passlib, PyJWT). The Vue 3 dashboard ships with the package.

### Install everything

```bash
pip install schedflow[web,sqlalchemy,mongodb,redis]
```

!!! tip "Faster installs with uv"
    ```bash
    uv pip install schedflow[web,sqlalchemy]
    ```

## Install from source

```bash
git clone https://github.com/freedomgod/schedflow.git
cd schedflow
pip install -e .[web,sqlalchemy,test]
```

## Verify the install

```python
import schedflow
print(schedflow.__version__)

from schedflow.core import Scheduler, Workflow


def hello() -> str:
    return "hello"


workflow = Workflow("smoke")
workflow.add_task("hello", func=hello)

scheduler = Scheduler()
scheduler.add_job(workflow, job_id="smoke_job")   # no trigger: manual runs only
log = scheduler.run_job_now("smoke_job")
print(log.records["hello"].result)                # hello
scheduler.shutdown()
```

## Building the docs (developers)

```bash
pip install -e .[doc]
mkdocs serve      # live preview at http://localhost:8000
mkdocs build      # build the static site into site/
```

## Next steps

- Follow the **[Quickstart](quickstart.md)** to build your first DAG workflow
- Read the **[User Guide](user-guide/core-features.md)** for the scheduler, triggers and stores
- Browse the **[API Reference](api-reference/index.md)** for the full interface
