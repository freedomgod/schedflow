"""Reject trigger payloads that would fire continuously.

A cron payload without any field matches *every second*, and a zero interval
keeps returning the current time. Both are almost always a half-filled form
rather than an intent, so the web API refuses them at the boundary; the
trigger classes keep the permissive semantics for programmatic callers (and
for pickling, which re-validates partially populated models).

An explicit ``second='*'`` or a positive interval still expresses the same
schedule on purpose.
"""

from __future__ import annotations

from typing import Any

from schedflow.exceptions.triggers import TriggerValidationError
from schedflow.triggers.cron import CRON_FIELD_NAMES

#: Interval arguments paired with their length in seconds.
_INTERVAL_FIELDS = (
    ("weeks", 7 * 86400),
    ("days", 86400),
    ("hours", 3600),
    ("minutes", 60),
    ("seconds", 1),
)

_COMBINING_TYPES = frozenset({"and", "or"})


def ensure_schedulable(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return ``payload`` unchanged, or raise when it has no usable schedule.

    Raises:
        TriggerValidationError: the payload would fire every second / never.
    """
    if not isinstance(payload, dict):
        return payload
    args = payload.get("args")
    if not isinstance(args, dict):
        return payload

    trigger_type = payload.get("type")
    if trigger_type == "cron":
        if not any(args.get(name) not in (None, "") for name in CRON_FIELD_NAMES):
            raise TriggerValidationError(
                "至少要填写一个 Cron 时间字段（年/月/日/周/星期几/时/分/秒），"
                "否则任务会每秒执行一次；确实需要每秒请显式把「秒」填成 *。",
                trigger_type="cron",
            )
    elif trigger_type == "interval":
        total_seconds = 0.0
        for name, factor in _INTERVAL_FIELDS:
            value = args.get(name) or 0
            try:
                total_seconds += float(value) * factor
            except (TypeError, ValueError):
                raise TriggerValidationError(
                    f"间隔字段「{name}」必须是数字，收到 {value!r}。",
                    trigger_type="interval",
                ) from None
        if total_seconds <= 0:
            raise TriggerValidationError(
                "Interval 触发器至少要设置一个大于 0 的间隔（周/天/时/分/秒），"
                "否则任务会连续触发。",
                trigger_type="interval",
            )
    elif trigger_type == "date":
        if not args.get("run_date"):
            raise TriggerValidationError(
                "Date 触发器需要设置运行时间（run_date），否则任务永远不会执行。",
                trigger_type="date",
            )
    elif trigger_type in _COMBINING_TYPES:
        nested = args.get("triggers")
        if isinstance(nested, list):
            for item in nested:
                ensure_schedulable(item)

    return payload
