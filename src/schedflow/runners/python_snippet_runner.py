"""Runner for python_script tasks — execute Python code snippets via subprocess."""

import os
import subprocess
import sys

from schedflow.core.result import TaskResult

from .base import BaseRunner, RunContext


class PythonSnippetRunner(BaseRunner):
    def run(self, spec, *, context: RunContext | None = None, **kwargs) -> TaskResult:
        context = context or RunContext()
        cmd = [sys.executable, '-c', spec.script]
        timeout = getattr(spec, "timeout", None) or context.timeout or 300
        env = {**os.environ, **context.env} if context.env else None
        cwd = str(context.cwd) if context.cwd is not None else None
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=cwd,
                check=False,
            )
            return TaskResult(
                succeeded=completed.returncode == 0,
                error=(completed.stderr or completed.stdout or f"Exit code: {completed.returncode}").strip() if completed.returncode != 0 else None,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired:
            return TaskResult(
                succeeded=False,
                error=f"Command timed out after {timeout}s",
                exit_code=-1,
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(succeeded=False, error=str(exc), exit_code=-1)
