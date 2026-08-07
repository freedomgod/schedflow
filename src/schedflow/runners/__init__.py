"""Task runner subsystem.

Runners are responsible for executing individual task nodes. They handle
different execution types (Python callable, script file, inline snippet, bash)
and return standardized TaskResult objects.
"""

from .base import TaskResult, BaseRunner
from .registry import RunnerRegistry
