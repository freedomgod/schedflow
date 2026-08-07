# DAG Workflows

The DAG workflow engine is the core differentiator of SchedFlow. This guide covers the complete `Workflow` API: nodes, edges, the execution model, result passing, conditional branching, serialization and execution logs.

## Workflow overview

A `Workflow` is a directed acyclic graph: **nodes are tasks, edges are dependencies**. It defines, validates and executes workflows directly, without a scheduler.

```python
from schedflow.core import Workflow

wf = Workflow("etl", project_root="./my_project")   # flow_id optional; project_root resolves relative path refs
```

## Adding task nodes (add_task)

```python
node_id = wf.add_task(
    "fetch",                          # node ID (unique per workflow, required)
    func=fetch_data,                  # a callable or a "module:function" string
    name="fetch",                     # optional readable name
    description="pull data from API", # optional description
    type="python_callable",           # task type, see the table below
    command=None,                     # shell command for type="bash"
    script_path=None,                 # .py script path for type="python"
    script=None,                      # inline code for type="python_script"
    args=[],                          # positional args (python_callable)
    kwargs={"source": "api"},         # keyword args
    retries=1,                        # max attempts (including the first)
    timeout=None,                     # per-attempt timeout in seconds
    on_success=None,                  # success callback (receives the return value)
    on_failure=None,                  # failure callback (receives the error message)
)
```

### Task types

| type | Required field | Execution |
|------|----------------|-----------|
| `python_callable` (default) | `func` (callable or string ref) | direct call in the current process |
| `python` | `script_path` | subprocess `python <script_path>` |
| `python_script` | `script` | subprocess `python -c <script>` |
| `bash` | `command` | subprocess shell command (falls back to `cmd /c` on Windows) |

```python
wf.add_task("bash_step", type="bash", command="echo hello && ls", timeout=30)
wf.add_task("script_step", type="python", script_path="./run.py", args=["--fast"])
wf.add_task("inline", type="python_script", script="print(sum(range(10)))")
```

Duplicate node IDs raise `ValueError`.

## Adding dependency edges (add_edge)

```python
wf.add_edge(
    "fetch",                # source node ID (must already exist)
    "process",              # target node ID (must already exist)
    condition=None,         # condition function or string ref: condition(record) -> bool
    name=None,              # optional
    description=None,       # optional
)
```

Adding an edge runs **cycle detection**: an edge that would create a cycle raises `CycleError` and is not written. Edges referencing unknown nodes are rejected too:

```python
from schedflow.core import CycleError

try:
    wf.add_edge("c", "a")          # if a→b→c already exists, this would create a cycle
except CycleError as exc:
    print(exc)                     # Edge 'c' -> 'a' would create a cycle; not added
```

### Disconnected ("island") nodes

`Workflow` **allows** nodes with no incoming or outgoing edges — they are not an error and serialize/persist normally. At execution time such nodes:

- have no prerequisites, so they land in **generation 0** and run in parallel with other root nodes (using one `max_workers` slot, with no `_pre_results` injected);
- still get a `TaskRecord` in the `ExecutionLog` and publish their `task.*` events;
- because **generations run sequentially**, a slow island node delays the whole workflow — generation 0 must finish entirely before the next generation starts;
- are not protected by isolation at the failure level: a failing island node marks the whole job `failed` (publishes `job.failed`), while the main chain keeps running unaffected.

If your intent is an independent task that should **not slow down or fail the main chain**, register it as a separate `Job` instead of putting it in the same workflow.

## Running directly (run)

```python
log = wf.run(
    max_workers=3,      # parallelism cap within a topological generation
    executor="thread",  # only thread execution is supported today (default)
    inputs={"api_key": "secret"},   # extra keyword args injected into every node
)
```

Execution model:

1. the DAG is **topologically sorted** and grouped into generations;
2. nodes in the same generation run in parallel (up to `max_workers`); generations run sequentially;
3. preconditions are checked: every predecessor must be `succeeded` and every incoming condition must be `True`; otherwise the node is marked `skipped`;
4. when all generations finish, an `ExecutionLog` is produced.

```text
    A ──→ C ──→ E
    ↓     ↓
    B ──→ D

generation 0: [A, B]   ← parallel
generation 1: [C, D]   ← parallel (after A, B)
generation 2: [E]      ← after C, D
```

!!! warning "Process execution"
    `Workflow.run()` currently supports only thread execution (`executor="process"` raises `NotImplementedError`). To run in processes, hand the workflow to a `Scheduler` with `ProcessPoolExecutor`, which rebuilds and runs the job in child processes.

## Predecessor results (_pre_results)

Downstream nodes receive the return values of all succeeded predecessors through the `_pre_results` keyword argument (node ID → result):

```python
def combine(_pre_results):
    total = sum(value["amount"] for value in _pre_results.values())
    return {"total": total}
```

The framework **filters arguments against the function signature**, so not declaring `_pre_results` never causes a `TypeError`.

## Conditional edges

A condition receives the upstream node's `TaskRecord` and returns `True` to allow or `False` to skip:

```python
def should_continue(record) -> bool:
    return record.status == "succeeded" and record.result.get("value", 0) > 100


wf.add_edge("check", "next", condition=should_continue)
```

When a condition is not met, the target node is marked `skipped` with a `skip_reason`. A failed predecessor also causes downstream nodes to be skipped; unaffected parallel branches keep running. If no node is `failed`, `log.succeeded` is `True` (`skipped` is not a failure).

## Retries, timeouts and callbacks

```python
def notify_success(retval):
    print("done:", retval)


def notify_failure(error):
    print("failed:", error)


wf.add_task(
    "flaky",
    func=flaky_func,
    retries=5,           # at most 5 attempts
    timeout=30,          # 30s per attempt
    on_success=notify_success,
    on_failure=notify_failure,
)
```

A node is marked `failed` only after retries are exhausted; callbacks run after the node status is recorded, and callback exceptions do not affect the node result.

## Execution logs (ExecutionLog)

Each run returns an `ExecutionLog`:

```python
log = wf.run()

log.log_id                 # auto-generated id (flowlog_xxx)
log.flow_id                # "etl"
log.job_id                 # set by the scheduler; None for direct runs
log.start_time / log.end_time / log.duration
log.succeeded              # True when no node failed
log.failed_nodes()         # [TaskRecord, ...]
log.skipped_nodes()        # [TaskRecord, ...]
log.records                # {node_id: TaskRecord}
log.dag_snapshot           # JSON snapshot of the DAG structure

record = log.records["fetch"]
record.status              # pending/running/succeeded/failed/skipped
record.result              # node return value
record.error               # failure reason
record.skip_reason         # skip reason
record.stdout / record.stderr / record.exit_code   # subprocess tasks
record.start_time / record.end_time / record.duration
```

## Serialization

```python
data = wf.to_dict()          # the single JSON export
restored = Workflow.from_dict(data)
```

Rules:

- string references (`ref`) are stored **verbatim** and never resolved on load;
- callables that cannot be converted to a reference (lambdas, nested closures) raise `ValueError` in `to_dict()` — use string references for persistence and cross-process scenarios;
- the run records a DAG snapshot into `log.dag_snapshot`; if snapshotting fails (e.g. lambdas), it degrades to nodes/edges structure only.

## Working with the scheduler

Definition and execution are decoupled: the same `Workflow` can be run directly, registered with a scheduler, or created through the Web API:

```python
scheduler.add_job(wf, trigger=IntervalTrigger(hours=1), job_id="etl_hourly")

# A JSON dict is equivalent (deserialized via from_dict first)
scheduler.add_job(wf.to_dict(), trigger=IntervalTrigger(hours=1), job_id="etl_hourly")
```
