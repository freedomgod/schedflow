"""Task runner subsystem.

Runners are responsible for executing individual task nodes. They handle
different execution types (Python callable, script file, inline snippet, bash)
and return standardized TaskResult objects.
"""

from .base import BaseRunner, TaskResult
from .registry import RunnerRegistry

__all__ = ["BaseRunner", "RunnerRegistry", "TaskResult"]
