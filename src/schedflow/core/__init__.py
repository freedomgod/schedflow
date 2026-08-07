"""Core objects for SchedFlow.

This package contains the user-facing building blocks of the library:
``TaskSpec`` (what a node executes), ``TaskResult`` (per-run outcome),
``TaskRecord`` / ``ExecutionLog`` (execution tracking) and ``Workflow``
(the DAG definition). Pydantic models from the legacy ``models`` package
are deliberately NOT exposed here.
"""

from schedflow.core.spec import TaskSpec
from schedflow.core.result import TaskResult
from schedflow.core.log import ExecutionLog, TaskRecord
from schedflow.core.workflow import CycleError, Workflow
from schedflow.core.events import EventBus, SchedulerEvent
from schedflow.core.job import Job
from schedflow.core.jobstore import (
    JobConflictError,
    JobNotFoundError,
    JobStore,
    MemoryJobStore,
)
from schedflow.core.executor import (
    DebugExecutor,
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from schedflow.core.scheduler import Scheduler

__all__ = (
    "TaskSpec",
    "TaskResult",
    "TaskRecord",
    "ExecutionLog",
    "Workflow",
    "CycleError",
    "EventBus",
    "SchedulerEvent",
    "Job",
    "JobConflictError",
    "JobNotFoundError",
    "JobStore",
    "MemoryJobStore",
    "DebugExecutor",
    "Executor",
    "ProcessPoolExecutor",
    "ThreadPoolExecutor",
    "Scheduler",
)
