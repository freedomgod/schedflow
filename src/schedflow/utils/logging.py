"""Logging configuration with an optional JSON formatter."""

from __future__ import annotations

import json
import logging
import os

_EXTRA_FIELDS = (
    "job_id",
    "execution_id",
    "node_id",
    "status",
    "duration_ms",
    "event",
)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in _EXTRA_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(force: bool = False) -> None:
    """Install the JSON formatter when ``SCHEDFLOW_LOG_FORMAT=json``."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, force=force)
    if os.environ.get("SCHEDFLOW_LOG_FORMAT", "text").lower() != "json":
        return
    root = logging.getLogger()
    formatter = JsonFormatter()
    for handler in root.handlers:
        handler.setFormatter(formatter)
