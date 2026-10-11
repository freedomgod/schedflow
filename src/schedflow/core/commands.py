"""Optimistic concurrency helpers for reviewed job commands."""

from __future__ import annotations

import hashlib
import json


class JobConfigConflictError(ValueError):
    """A reviewed job configuration no longer matches the live job."""


def config_hash(data: dict) -> str:
    """Hash full JSON job configuration, excluding its moving fire time."""
    configuration = {
        key: value for key, value in data.items() if key != "next_run_time"
    }
    encoded = json.dumps(
        configuration,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
