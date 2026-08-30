"""Runner for bash tasks — execute shell commands via subprocess."""

import os
import shutil
import subprocess
import sys

from schedflow.core.result import TaskResult

from .base import BaseRunner, RunContext


def _is_wsl_shell(path):
    """Detect if a bash/sh path is the WSL stub (won't work directly)."""
    if not path or sys.platform != 'win32':
        return False
    return '\\windows\\' in os.path.realpath(path).lower()


def _find_shell():
    """Locate a working shell. On Windows skips WSL bash, falls back to cmd."""
    for name in ('bash', 'sh'):
        path = shutil.which(name)
        if path and not _is_wsl_shell(path):
            return path

    if sys.platform == 'win32':
        # Search common Git Bash / MSYS2 locations
        for base in (
            r'C:\Program Files\Git\bin',
            r'C:\Program Files (x86)\Git\bin',
            r'C:\Program Files\Git\usr\bin',
            r'C:\msys64\usr\bin',
        ):
            for name in ('bash.exe', 'sh.exe'):
                p = os.path.join(base, name)
                if os.path.isfile(p):
                    return p
        # Search all drive roots for Git\bin\bash.exe
        for drive in 'CDEFGH':
            p = f'{drive}:\\Git\\bin\\bash.exe'
            if os.path.isfile(p):
                return p
            p = f'{drive}:\\Git\\usr\\bin\\bash.exe'
            if os.path.isfile(p):
                return p

    return None


class BashRunner(BaseRunner):
    def run(self, spec, *, context: RunContext | None = None, **kwargs) -> TaskResult:
        context = context or RunContext()
        shell = _find_shell()

        if shell:
            cmd = [shell, '-lc', spec.command]
        elif sys.platform == 'win32':
            # Fall back to cmd.exe on Windows when no bash is available
            cmd = ['cmd', '/c', spec.command]
        else:
            return TaskResult(
                succeeded=False,
                error="bash/sh not found. Install bash or add it to PATH.",
                exit_code=-1,
            )

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
                error=(completed.stderr or completed.stdout or f"Exit code: {completed.returncode}").strip()
                if completed.returncode != 0 else None,
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
