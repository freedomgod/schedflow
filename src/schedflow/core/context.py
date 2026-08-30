"""Execution context shared by workflow execution and runners."""

from __future__ import annotations

import logging
from pathlib import Path


class RunContext:
    """Execution context: the only external dependency of a runner.

    Attributes:
        project_root: base directory for relative path references.
        env: extra environment variables for subprocess-based tasks.
        cwd: working directory for subprocess-based tasks.
        timeout: default timeout (seconds) for subprocess-based tasks.
        logger: logger used for execution diagnostics.
    """

    __slots__ = ("cwd", "env", "logger", "project_root", "timeout")

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        env: dict | None = None,
        cwd: str | Path | None = None,
        timeout: float | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.project_root = (
            Path(project_root) if project_root is not None else None
        )
        self.env = dict(env or {})
        self.cwd = Path(cwd) if cwd is not None else None
        self.timeout = timeout
        self.logger = logger or logging.getLogger("schedflow.runner")
