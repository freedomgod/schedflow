"""System default timezone glue for the web layer.

Triggers resolve an omitted timezone from the *operating system's* local zone,
which is ``Etc/UTC`` inside a container that does not set ``TZ``. That default
is wrong for the person filling in a cron expression, so the web layer fills in
the operator-configured timezone (``GET/PUT /api/v1/settings/timezone``)
before a trigger is constructed.

Precedence, highest first:

1. an explicit ``timezone`` in the trigger payload,
2. the persisted system default,
3. the process-local zone the trigger falls back to on its own.
"""

from __future__ import annotations

from typing import Any

from schedflow.core.scheduler import Scheduler
from schedflow.settings.services import get_configured_timezone, get_default_timezone

#: Trigger types that accept a top-level ``timezone`` argument.
TIMEZONE_AWARE_TYPES = frozenset(
    {"cron", "interval", "date", "calendarinterval"}
)

#: Trigger types that nest other triggers under ``args["triggers"]``.
COMBINING_TYPES = frozenset({"and", "or"})


def apply_scheduler_timezone(
    scheduler: Scheduler, *, include_reset: bool = False
) -> None:
    """Point the live scheduler at the configured zone.

    At startup (``include_reset=False``) an unset setting is a no-op, so a
    programmatically created ``Scheduler(timezone=...)`` is never silently
    overridden. An explicit settings change passes ``include_reset=True``:
    clearing the setting has to move the scheduler back to the process-local
    zone instead of leaving the previously configured value behind.
    """
    configured = get_configured_timezone()
    if configured:
        scheduler.set_timezone(configured)
    elif include_reset:
        scheduler.set_timezone(None)


def with_default_timezone(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return ``{"type": ..., "args": {...}}`` with the default timezone filled in.

    Payloads that already carry a timezone -- and trigger types that have no
    such argument -- are returned unchanged. Combining triggers are handled
    recursively so nested cron/interval triggers inherit the default too.
    """
    if not isinstance(payload, dict):
        return payload
    args = payload.get("args")
    if not isinstance(args, dict):
        return payload

    trigger_type = payload.get("type")
    if trigger_type in COMBINING_TYPES:
        nested = args.get("triggers")
        if isinstance(nested, list):
            return {
                **payload,
                "args": {
                    **args,
                    "triggers": [with_default_timezone(item) for item in nested],
                },
            }
        return payload

    if trigger_type not in TIMEZONE_AWARE_TYPES or args.get("timezone"):
        return payload

    return {
        **payload,
        "args": {**args, "timezone": get_default_timezone()},
    }
