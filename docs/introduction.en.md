# Introduction

## What is SchedFlow?

SchedFlow is a lightweight **scheduled task workflow framework**. It ships its own scheduling core with the familiar building blocks — triggers (when to run), executors (how to run), job stores (where state persists) and a background scheduling loop — and upgrades "a job = a function call" to "a job = a DAG workflow graph".

The underlying interfaces follow an explicit, unified design:

- **Explicit API**: every public method uses explicit keyword signatures with full IDE hints — no `*args/**kwargs` magic, no `model=None, **kwargs` passthrough;
- **Plain Python objects**: users only interact with `Workflow`, `TaskSpec`, `Trigger`, `Job`, `Scheduler`, `JobStore` and `Executor`; Pydantic models moved to the internal serialization layer;
- **Lazy reference resolution**: `func` accepts a callable or a `"module:function"` string; strings are resolved only at execution time, so creating, persisting or restarting a job never fails because a module is missing;
- **No `add_job(func, trigger, ...)`-style interface**: there is no `scheduled_job` decorator; the API is designed around this library's semantics.

## Motivation

Consider a typical data pipeline:

```text
extract → transform → validate → load
                              ↘ notify
```

With a plain "one job = one function call" scheduler you have to orchestrate these steps by hand — chaining callbacks, coordinating parallelism, handling partial failures and collecting execution logs. SchedFlow builds these capabilities into the framework:

- **Declarative dependencies** — declare dependencies between tasks as a DAG;
- **Automatic parallelism** — independent tasks in the same topological generation run in parallel;
- **Failure propagation** — downstream nodes are marked `skipped` when an upstream node fails or a conditional edge is not satisfied;
- **Execution tracking** — every run produces a structured `ExecutionLog` with per-node status, result, error and timing;
- **Retries** — per-node retry counts, timeouts and success/failure callbacks;
- **Multiple task types** — mix Python functions, `.py` scripts, inline snippets and shell commands in one workflow.

## Architecture

```text
┌──────────────────────────────────────────┐
│            Vue 3 dashboard               │  ← DAG editor, job management, logs
├──────────────────────────────────────────┤
│            FastAPI Web API (/api)        │  ← structured JSON, unified responses
├──────────────────────────────────────────┤
│   Workflow (DAG engine)                  │  ← topological sort, conditional edges,
│   TaskSpec / Runner                      │     parallel groups, cycle detection
│   ExecutionLog                           │
├──────────────────────────────────────────┤
│   Scheduler → Trigger → JobStore         │  ← scheduling loop, triggers, persistence
│                     → Executor           │  ← thread / process execution
└──────────────────────────────────────────┘
```

### Core objects

**Workflow** — the main object you define. Add nodes with `add_task()` and conditional dependency edges with `add_edge()`, run it directly with `run()`, and serialize with `to_dict()/from_dict()`. Cycles raise `CycleError` at `add_edge()` time.

**TaskSpec** — describes what one node executes. Four execution types: `python_callable` (a function or string reference), `python` (run a `.py` file in a subprocess), `python_script` (inline code via `python -c`), `bash` (shell command). You normally build specs through `Workflow.add_task()`.

**Trigger** — decides *when* a job runs: `DateTrigger` (once), `IntervalTrigger` (fixed interval), `CronTrigger` (cron-style expressions), `CalendarIntervalTrigger` (calendar-aligned), `AndTrigger`/`OrTrigger` (combinations). All use explicit keyword construction and support `to_dict()/from_dict()`.

**Job** — the top-level scheduling unit, binding a `Workflow` to a trigger, executor alias, jobstore alias and misfire policy.

**Scheduler** — runs the main loop: pulls due jobs from the job store, computes next run times, submits jobs to the executor, publishes events and persists execution logs. The project uses a single `schedflow.core.Scheduler` implementation (the main loop runs in a background thread) with multi-executor / multi-jobstore alias routing; the legacy `schedflow.schedulers` package has been removed.

**JobStore** — persistence interface for jobs and logs, with `MemoryJobStore`, `SQLAlchemyJobStore`, `RedisJobStore` and `MongoDBJobStore`. All use JSON (no pickle) and never resolve string references on load.

**Executor** — decides *how* a job runs: `ThreadPoolExecutor` (default), `ProcessPoolExecutor` (JSON worker protocol, works on Windows), `DebugExecutor` (synchronous, for tests), and more.

**ExecutionLog** — the complete record of one run: `log_id`, `flow_id`, `job_id`, start/end times, per-node `TaskRecord` entries (status, result, error, stdout/stderr, exit code, duration) and a DAG snapshot.

## Data flow

```text
define Workflow (add_task / add_edge)
      │
scheduler.add_job(workflow, trigger=..., job_id=...)   → JobStore (JSON)
      │
scheduler.start() → main loop: get_due(now) → next run time → executor.submit(job, run_time)
      │
executor calls job.run() → workflow.run(max_workers=...) → generations, parallel within
      │
ExecutionLog → jobstore.add_log() → job.succeeded / job.failed events
      │
consumed by Web API / frontend: /api/jobs, /api/jobs/{id}/logs
```

## Project status

- The core (Workflow / Trigger / Job / Scheduler / JobStore / Executor / Web API) is usable and tested;
- the project is under active development — see the [changelog](changelog.md) for feature history.
