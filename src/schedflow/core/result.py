"""Task execution result container."""

from __future__ import annotations

from typing import Any


class TaskResult:
    """Outcome of running a single task.

    Attributes:
        succeeded: whether the task completed without error.
        result: the return value of the task (if any).
        error: the exception message (if failed).
        exit_code: process exit code for subprocess-based tasks.
        stdout / stderr: captured output for subprocess-based tasks.
        duration: wall-clock execution time in seconds (if available).
    """

    __slots__ = (
        "duration",
        "error",
        "exit_code",
        "result",
        "stderr",
        "stdout",
        "succeeded",
    )

    def __init__(
        self,
        succeeded: bool,
        result: Any = None,
        error: str | None = None,
        exit_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        duration: float | None = None,
    ) -> None:
        self.succeeded = succeeded
        self.result = result
        self.error = error
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

    def to_dict(self) -> dict:
        return {
            "succeeded": self.succeeded,
            "result": self.result,
            "error": self.error,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskResult:
        return cls(
            succeeded=data["succeeded"],
            result=data.get("result"),
            error=data.get("error"),
            exit_code=data.get("exit_code"),
            stdout=data.get("stdout"),
            stderr=data.get("stderr"),
            duration=data.get("duration"),
        )

    def __repr__(self) -> str:
        return (
            f"<TaskResult succeeded={self.succeeded} result={self.result!r} "
            f"error={self.error!r}>"
        )
