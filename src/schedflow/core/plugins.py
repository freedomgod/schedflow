"""Static component registry (replaces entry-point discovery).

The legacy stack registered triggers/executors/jobstores through
``project.entry-points`` in ``pyproject.toml``. The single-stack system keeps
one explicit registry per component family so the component set is stable and
importable without package metadata.
"""

from __future__ import annotations

from schedflow.core.async_executors import (
    AsyncIOExecutor,
    GeventExecutor,
    TornadoExecutor,
    TwistedExecutor,
)
from schedflow.core.executor import (
    DebugExecutor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from schedflow.core.jobstore import MemoryJobStore
from schedflow.core.stores.mongo import MongoDBJobStore
from schedflow.core.stores.redis import RedisJobStore
from schedflow.core.stores.sqlalchemy import SQLAlchemyJobStore

EXECUTOR_PLUGINS: dict[str, type] = {
    "debug": DebugExecutor,
    "threadpool": ThreadPoolExecutor,
    "processpool": ProcessPoolExecutor,
    "asyncio": AsyncIOExecutor,
    "gevent": GeventExecutor,
    "tornado": TornadoExecutor,
    "twisted": TwistedExecutor,
}

JOBSTORE_PLUGINS: dict[str, type] = {
    "memory": MemoryJobStore,
    "sqlalchemy": SQLAlchemyJobStore,
    "redis": RedisJobStore,
    "mongodb": MongoDBJobStore,
}
