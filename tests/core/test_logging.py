"""Structured logging tests."""

import json
import logging

from schedflow.utils.logging import JsonFormatter, configure_logging


def test_json_formatter_includes_message_and_extra_fields():
    record = logging.LogRecord(
        "schedflow.test",
        logging.INFO,
        __file__,
        1,
        "job finished",
        (),
        None,
    )
    record.job_id = "j1"
    record.node_id = "n1"
    record.status = "succeeded"
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "job finished"
    assert payload["job_id"] == "j1"
    assert payload["node_id"] == "n1"
    assert payload["status"] == "succeeded"
    assert payload["duration_ms"] == 12.5
    assert payload["level"] == "INFO"


def test_configure_logging_json(monkeypatch):
    monkeypatch.setenv("SCHEDFLOW_LOG_FORMAT", "json")

    configure_logging(force=True)

    root = logging.getLogger()
    assert root.handlers
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
