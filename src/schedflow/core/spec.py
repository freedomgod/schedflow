"""Task specification model (internal serialization layer).

``TaskSpec`` describes what a workflow node executes. Users normally build it
through ``Workflow.add_task(...)`` and never construct it directly, but it is
the single source of truth for the JSON contract between the Python SDK,
job stores and the Web API.

Supported execution types:

- ``python_callable``: call a Python function. Accepts either a callable
  object or a ``"module:function"`` string reference. String references are
  stored verbatim and resolved lazily at execution time (never at
  construction/serialization time).
- ``bash``: run a shell command.
- ``python``: run a ``.py`` script file with ``python <script_path>``.
- ``python_script``: run inline Python code with ``python -c <script>``.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from schedflow.utils import obj_to_ref

TaskType = Literal["python_callable", "bash", "python", "python_script"]

_VALID_TYPES = ("python_callable", "bash", "python", "python_script")


class TaskSpec:
    """A serializable description of what one workflow node executes."""

    __slots__ = (
        "type",
        "ref",
        "func",
        "command",
        "script_path",
        "script",
        "args",
        "kwargs",
        "timeout",
    )

    def __init__(
        self,
        func: Optional[Callable | str] = None,
        *,
        type: str = "python_callable",
        command: Optional[str] = None,
        script_path: Optional[str] = None,
        script: Optional[str] = None,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if type not in _VALID_TYPES:
            raise ValueError(
                f"Unknown task type {type!r}; expected one of {_VALID_TYPES}"
            )
        self.type = type
        self.ref: Optional[str] = None
        self.func: Optional[Callable] = None
        self.command = command
        self.script_path = script_path
        self.script = script
        self.args = list(args or [])
        self.kwargs = dict(kwargs or {})
        self.timeout = timeout

        if type == "python_callable":
            if isinstance(func, str):
                self.ref = func
            elif func is not None:
                self.func = func
            if self.ref is None and self.func is None:
                raise ValueError(
                    "For 'python_callable' type, 'func' or a 'module:func' "
                    "string reference must be provided"
                )
        elif type == "bash":
            if not command:
                raise ValueError("For 'bash' type, 'command' must be provided")
        elif type == "python":
            if not script_path:
                raise ValueError("For 'python' type, 'script_path' must be provided")
        elif type == "python_script":
            if not script:
                raise ValueError("For 'python_script' type, 'script' must be provided")

    def to_dict(self) -> dict:
        """Serialize to the canonical JSON structure.

        ``python_callable`` specs serialize as ``ref``; a callable without a
        resolvable reference (e.g. a lambda) raises ``ValueError``.
        """
        data: dict = {
            "type": self.type,
            "args": self.args,
            "kwargs": self.kwargs,
            "timeout": self.timeout,
        }
        if self.type == "python_callable":
            if self.ref is not None:
                data["ref"] = self.ref
            else:
                data["ref"] = obj_to_ref(self.func)
        elif self.type == "bash":
            data["command"] = self.command
        elif self.type == "python":
            data["script_path"] = self.script_path
        elif self.type == "python_script":
            data["script"] = self.script
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        """Rebuild a spec from JSON without resolving any reference."""
        return cls(
            func=data.get("ref"),
            type=data.get("type", "python_callable"),
            command=data.get("command"),
            script_path=data.get("script_path"),
            script=data.get("script"),
            args=data.get("args"),
            kwargs=data.get("kwargs"),
            timeout=data.get("timeout"),
        )

    def __repr__(self) -> str:
        return f"<TaskSpec type={self.type!r} ref={self.ref!r}>"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TaskSpec):
            return NotImplemented
        return self.to_dict() == other.to_dict()
