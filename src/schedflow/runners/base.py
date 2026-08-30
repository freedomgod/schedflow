"""Runner interface and execution context."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schedflow.core.result import TaskResult

from schedflow.core.context import RunContext
from schedflow.core.result import TaskResult


class BaseRunner(ABC):
    """Abstract base class for task runners.

    Subclasses implement ``run()`` for one execution type. Runners receive a
    task spec (the core ``TaskSpec``; legacy ``CallableModel`` is tolerated via
    attribute access) plus a :class:`RunContext`, and always return a
    ``TaskResult`` instead of raising.
    """

    @abstractmethod
    def run(self, spec, *, context: RunContext | None = None, **kwargs) -> "TaskResult":
        """Execute a task described by ``spec``.

        Args:
            spec (TaskSpec or legacy CallableModel): the task specification.
            context (RunContext): execution context (project root, env, cwd, timeout).
            **kwargs (dict): runtime keyword arguments, overriding ``spec.kwargs``.

        Returns:
            A TaskResult with succeeded=True on success, or
            succeeded=False with error details on failure.
        """
        ...
