"""Workflow DAG object."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Callable, Optional

import networkx as nx

from schedflow.core.log import ExecutionLog, TaskRecord
from schedflow.core.context import RunContext
from schedflow.core.result import TaskResult
from schedflow.core.resolve import resolve_ref
from schedflow.core.spec import TaskSpec


class CycleError(Exception):
    """Raised when adding an edge would create a cycle in the workflow."""


class _Node:
    __slots__ = ("spec", "name", "description", "retries", "on_success", "on_failure")

    def __init__(
        self,
        spec: TaskSpec,
        name: Optional[str],
        description: Optional[str],
        retries: int,
        on_success: Optional[TaskSpec],
        on_failure: Optional[TaskSpec],
    ) -> None:
        self.spec = spec
        self.name = name
        self.description = description
        self.retries = max(1, int(retries or 1))
        self.on_success = on_success
        self.on_failure = on_failure


class _Edge:
    __slots__ = ("source", "target", "condition", "name", "description")

    def __init__(
        self,
        source: str,
        target: str,
        condition: Optional[TaskSpec],
        name: Optional[str],
        description: Optional[str],
    ) -> None:
        self.source = source
        self.target = target
        self.condition = condition
        self.name = name
        self.description = description


def _to_callable_spec(value) -> Optional[TaskSpec]:
    """Normalize a callback/condition to a python_callable TaskSpec (or None)."""
    if value is None:
        return None
    if isinstance(value, TaskSpec):
        return value
    return TaskSpec(func=value)


class Workflow:
    """A DAG workflow: nodes are tasks, edges are dependencies (optionally
    guarded by a condition evaluated against the upstream ``TaskRecord``)."""

    def __init__(
        self,
        flow_id: Optional[str] = None,
        *,
        project_root: Optional[str | Path] = None,
    ) -> None:
        self.flow_id = flow_id
        self.project_root = (
            Path(project_root) if project_root is not None else None
        )
        self._nodes: dict[str, _Node] = {}
        self._edges: list[_Edge] = []

    # ── definition ─────────────────────────────────────────────────────

    def add_task(
        self,
        node_id: str,
        func: Optional[Callable | str] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        type: str = "python_callable",
        command: Optional[str] = None,
        script_path: Optional[str] = None,
        script: Optional[str] = None,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        retries: int = 1,
        timeout: Optional[float] = None,
        on_success: Optional[Callable | str | TaskSpec] = None,
        on_failure: Optional[Callable | str | TaskSpec] = None,
    ) -> str:
        """Add a task node.

        ``func`` accepts a callable or a ``"module:function"`` string
        reference (stored verbatim, resolved at execution time). For
        non-python_callable types use the matching field: ``command`` for
        ``bash``, ``script_path`` for ``python``, ``script`` for
        ``python_script``.

        Returns the ``node_id``.
        """
        if not node_id or not isinstance(node_id, str):
            raise ValueError("node_id must be a non-empty string")
        if node_id in self._nodes:
            raise ValueError(f"Task node {node_id!r} already exists")
        spec = TaskSpec(
            func=func,
            type=type,
            command=command,
            script_path=script_path,
            script=script,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )
        self._nodes[node_id] = _Node(
            spec=spec,
            name=name,
            description=description,
            retries=retries,
            on_success=_to_callable_spec(on_success),
            on_failure=_to_callable_spec(on_failure),
        )
        return node_id

    def add_edge(
        self,
        source: str,
        target: str,
        *,
        condition: Optional[Callable | str | TaskSpec] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Add a dependency edge (with cycle detection).

        ``condition``, when provided, is called with the upstream
        ``TaskRecord`` and must return True for the target to run.
        """
        for endpoint, label in ((source, "source"), (target, "target")):
            if endpoint not in self._nodes:
                raise ValueError(
                    f"Unknown {label} node {endpoint!r}; add it with add_task() first"
                )
        edge = _Edge(
            source=source,
            target=target,
            condition=_to_callable_spec(condition),
            name=name,
            description=description,
        )
        graph = self._to_graph()
        graph.add_edge(source, target)
        if not nx.is_directed_acyclic_graph(graph):
            raise CycleError(
                f"Edge {source!r} -> {target!r} would create a cycle; not added"
            )
        self._edges.append(edge)

    def validate(self) -> None:
        """Validate structure: node ids, edge endpoints, no cycles."""
        if not nx.is_directed_acyclic_graph(self._to_graph()):
            raise CycleError("Workflow contains a cycle")

    # ── execution ──────────────────────────────────────────────────────

    def run(
        self,
        *,
        max_workers: int = 3,
        executor: str = "thread",
        inputs: Optional[dict] = None,
    ) -> ExecutionLog:
        """Execute the workflow directly (without a scheduler).

        Nodes in the same topological generation run in parallel (up to
        ``max_workers``); generations run sequentially. Predecessors must
        succeed and edge conditions must be True, otherwise the target is
        marked SKIPPED. Upstream results are injected into the downstream
        function as a ``_pre_results`` keyword argument when accepted.
        """
        if executor != "thread":
            raise NotImplementedError(
                "process execution is handled by the scheduler's "
                "ProcessPoolExecutor, not by Workflow.run()"
            )

        log = ExecutionLog(flow_id=self.flow_id)
        log.dag_snapshot = self._snapshot()
        log.records = {
            node_id: TaskRecord(node_id=node_id, task_id=node_id)
            for node_id in self._nodes
        }

        for generation in self._generations():
            self._execute_generation(
                generation,
                log=log,
                max_workers=max_workers,
                inputs=inputs or {},
            )
        log.finalize()
        return log

    def _snapshot(self) -> dict:
        """Best-effort DAG snapshot for execution logs.

        Workflows containing lambdas or nested functions cannot be fully
        serialized (no stable reference); in that case only the structural
        shape is recorded so the log remains JSON-safe.
        """
        try:
            return self.to_dict()
        except (TypeError, ValueError):
            return {
                "flow_id": self.flow_id,
                "nodes": [{"node_id": node_id} for node_id in self._nodes],
                "edges": [
                    {"source": edge.source, "target": edge.target}
                    for edge in self._edges
                ],
            }

    def _execute_generation(
        self,
        generation: list[str],
        *,
        log: ExecutionLog,
        max_workers: int,
        inputs: dict,
    ) -> None:
        futures: dict[concurrent.futures.Future, str] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        ) as pool:
            for node_id in generation:
                if not self._check_preconditions(node_id, log):
                    reason = self._skip_reason(node_id, log)
                    log.records[node_id].mark_skipped(reason)
                    continue
                # Mark started before the node actually runs so the recorded
                # duration covers the real execution window.
                log.records[node_id].mark_started()
                kwargs = self._build_kwargs(node_id, log, inputs)
                future = pool.submit(self._execute_node, node_id, kwargs)
                futures[future] = node_id

            for future in concurrent.futures.as_completed(futures):
                node_id = futures[future]
                result = future.result()
                self._apply_result(node_id, result, log)

    def _execute_node(self, node_id: str, kwargs: dict) -> TaskResult:
        node = self._nodes[node_id]
        spec = node.spec
        context = RunContext(project_root=self.project_root or Path.cwd())
        # Imported lazily to avoid a module-level import cycle between
        # core.workflow and runners (runners re-export core.result, which
        # triggers the core package initializer).
        from schedflow.runners.registry import RunnerRegistry

        runner = RunnerRegistry.get(spec.type)
        last_result = TaskResult(
            succeeded=False,
            error=f"Task {node_id!r} did not run",
        )
        for _attempt in range(node.retries):
            last_result = runner.run(spec, context=context, **kwargs)
            if last_result.succeeded:
                return last_result
        return last_result

    def _apply_result(
        self, node_id: str, result: TaskResult, log: ExecutionLog
    ) -> None:
        record = log.records[node_id]
        node = self._nodes[node_id]
        if result.succeeded:
            record.mark_succeeded(result=result.result)
            if node.on_success is not None:
                self._call_callback(node.on_success, result.result)
        else:
            record.mark_failed(result.error or "Task failed")
            if node.on_failure is not None:
                self._call_callback(node.on_failure, record.error)
        record.stdout = result.stdout
        record.stderr = result.stderr
        record.exit_code = result.exit_code

    def _call_callback(self, spec: TaskSpec, value) -> None:
        func = spec.func
        if func is None:
            func = resolve_ref(
                spec.ref, project_root=self.project_root or Path.cwd()
            )
        func(value)

    def _check_preconditions(self, node_id: str, log: ExecutionLog) -> bool:
        for edge in self._edges:
            if edge.target != node_id:
                continue
            upstream = log.records[edge.source]
            if upstream.status != "succeeded":
                return False
            if edge.condition is not None:
                condition = edge.condition.func
                if condition is None:
                    condition = resolve_ref(
                        edge.condition.ref,
                        project_root=self.project_root or Path.cwd(),
                    )
                if not condition(upstream):
                    return False
        return True

    def _skip_reason(self, node_id: str, log: ExecutionLog) -> str:
        reasons = []
        for edge in self._edges:
            if edge.target != node_id:
                continue
            upstream = log.records[edge.source]
            if upstream.status != "succeeded":
                reasons.append(f"predecessor {edge.source!r} did not succeed")
            elif edge.condition is not None:
                reasons.append(f"condition on edge {edge.source!r}->{node_id!r} not met")
        return "; ".join(reasons) or "dependency failed"

    def _build_kwargs(
        self, node_id: str, log: ExecutionLog, inputs: dict
    ) -> dict:
        kwargs = dict(inputs)
        predecessors = [
            edge.source
            for edge in self._edges
            if edge.target == node_id
            and log.records[edge.source].status == "succeeded"
        ]
        if predecessors:
            kwargs["_pre_results"] = {
                source: log.records[source].result for source in predecessors
            }
        return kwargs

    def _generations(self) -> list[list[str]]:
        graph = self._to_graph()
        indegree = {v: d for v, d in graph.in_degree() if d > 0}
        zero = [v for v, d in graph.in_degree() if d == 0]
        generations = []
        while zero:
            generations.append(zero)
            new_zero = []
            for node in zero:
                for child in graph.successors(node):
                    indegree[child] = indegree.get(child, 0) - 1
                    if indegree[child] == 0:
                        new_zero.append(child)
            zero = new_zero
        return generations

    def _to_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        graph.add_nodes_from(self._nodes)
        graph.add_edges_from((edge.source, edge.target) for edge in self._edges)
        return graph

    # ── serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "project_root": (
                str(self.project_root) if self.project_root is not None else None
            ),
            "nodes": [
                {
                    "node_id": node_id,
                    "task": node.spec.to_dict(),
                    "name": node.name,
                    "description": node.description,
                    "retries": node.retries,
                    "on_success": (
                        node.on_success.to_dict()
                        if node.on_success is not None
                        else None
                    ),
                    "on_failure": (
                        node.on_failure.to_dict()
                        if node.on_failure is not None
                        else None
                    ),
                }
                for node_id, node in self._nodes.items()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "condition": (
                        edge.condition.to_dict()
                        if edge.condition is not None
                        else None
                    ),
                    "name": edge.name,
                    "description": edge.description,
                }
                for edge in self._edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        wf = cls(
            flow_id=data.get("flow_id"),
            project_root=data.get("project_root"),
        )
        for node in data.get("nodes", []):
            spec = TaskSpec.from_dict(node["task"])
            wf.add_task(
                node["node_id"],
                func=spec.ref if spec.type == "python_callable" else None,
                type=spec.type,
                command=spec.command,
                script_path=spec.script_path,
                script=spec.script,
                args=spec.args,
                kwargs=spec.kwargs,
                timeout=spec.timeout,
                name=node.get("name"),
                description=node.get("description"),
                retries=node.get("retries", 1),
                on_success=_spec_from_json(node.get("on_success")),
                on_failure=_spec_from_json(node.get("on_failure")),
            )
        for edge in data.get("edges", []):
            wf.add_edge(
                edge["source"],
                edge["target"],
                condition=_spec_from_json(edge.get("condition")),
                name=edge.get("name"),
                description=edge.get("description"),
            )
        return wf

    def __repr__(self) -> str:
        return (
            f"<Workflow flow_id={self.flow_id!r} "
            f"nodes={len(self._nodes)} edges={len(self._edges)}>"
        )


def _spec_from_json(value) -> Optional[TaskSpec]:
    if value is None:
        return None
    return TaskSpec.from_dict(value)
