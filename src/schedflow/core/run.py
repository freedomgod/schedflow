"""Per-run options passed from the scheduler through executors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRequest:
    mode: str = "full"
    timeout: float | None = None
    resume_execution_id: str | None = None
    resume_snapshot: dict | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"full", "resume"}:
            raise ValueError(f"Unknown run mode {self.mode!r}")

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "timeout": self.timeout,
            "resume_execution_id": self.resume_execution_id,
            "resume_snapshot": self.resume_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> RunRequest:
        data = data or {}
        return cls(
            mode=data.get("mode", "full"),
            timeout=data.get("timeout"),
            resume_execution_id=data.get("resume_execution_id"),
            resume_snapshot=data.get("resume_snapshot"),
        )
