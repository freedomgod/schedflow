"""Runner registry for automatic runner lookup by execution type."""

from typing import ClassVar

from schedflow.runners.base import BaseRunner


class RunnerRegistry:
    """Registry mapping CallableModel.type strings to BaseRunner instances.

    Usage::

        runner = RunnerRegistry.get("python_callable")
        result = runner.run(callable_model, **kwargs)
    """

    _runners: ClassVar[dict] = {}

    @classmethod
    def register(cls, type_name: str, runner):
        """Register a runner instance for a task type.

        Args:
            type_name: The CallableModel.type string.
            runner (BaseRunner): A BaseRunner instance.
        """
        cls._runners[type_name] = runner

    @classmethod
    def get(cls, type_name: str) -> BaseRunner:
        """Look up the runner instance for a given task type.

        Args:
            type_name: One of 'python_callable', 'python', 'python_script', 'bash'.

        Returns:
            BaseRunner: The instance registered for this type.

        Raises:
            ValueError: If no runner is registered for the given type.
        """
        if type_name not in cls._runners:
            raise ValueError(
                f"Unknown task type '{type_name}'. "
                f"Available types: {list(cls._runners.keys())}"
            )
        return cls._runners[type_name]

    @classmethod
    def list_types(cls) -> list:
        """Return all registered task type names.

        Returns:
            A list of registered type name strings.
        """
        return list(cls._runners.keys())


# Auto-register all runners on module import.
from .bash_runner import BashRunner
from .python_callable_runner import PythonCallableRunner
from .python_file_runner import PythonFileRunner
from .python_snippet_runner import PythonSnippetRunner

RunnerRegistry.register('python_callable', PythonCallableRunner())
RunnerRegistry.register('bash', BashRunner())
RunnerRegistry.register('python', PythonFileRunner())
RunnerRegistry.register('python_script', PythonSnippetRunner())
