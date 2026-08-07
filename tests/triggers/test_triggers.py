"""trigger API tests: explicit constructors + JSON registry."""

from datetime import datetime, timezone

import pytest

from schedflow.triggers import (
    AndTrigger,
    CalendarIntervalTrigger,
    CronTrigger,
    DateTrigger,
    IntervalTrigger,
    OrTrigger,
)
from schedflow.triggers.base import Trigger


def test_interval_explicit_keyword_signature():
    trigger = IntervalTrigger(seconds=30)
    assert trigger.seconds == 30


def test_interval_rejects_trigger_model_parameter():
    with pytest.raises(TypeError):
        IntervalTrigger(trigger_model={})  # type: ignore[call-arg]


def test_interval_next_fire_time():
    trigger = IntervalTrigger(seconds=60)
    now = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    next_time = trigger.get_next_fire_time(None, now)
    assert next_time is not None
    assert next_time > now


def test_date_explicit_keyword_signature():
    run_at = datetime(2026, 8, 1, 10, 0)
    trigger = DateTrigger(run_date=run_at)
    assert trigger.run_date is not None


def test_cron_explicit_keyword_signature():
    trigger = CronTrigger(hour=10, minute=30, day_of_week="mon-fri")
    next_time = trigger.get_next_fire_time(
        None, datetime(2026, 8, 1, 0, 0)
    )
    assert next_time is not None


def test_calendar_interval_explicit_keyword_signature():
    trigger = CalendarIntervalTrigger(days=1, hour=8, minute=0)
    assert trigger.days == 1


def test_trigger_to_dict_and_from_dict_roundtrip():
    trigger = IntervalTrigger(seconds=30)
    data = trigger.to_dict()
    assert data["type"] == "interval"

    restored = Trigger.from_dict(data)
    assert isinstance(restored, IntervalTrigger)
    assert restored.seconds == 30


def test_trigger_from_dict_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown trigger type"):
        Trigger.from_dict({"type": "unknown", "args": {}})


def test_date_trigger_roundtrip():
    trigger = DateTrigger(run_date=datetime(2026, 8, 1, 10, 0))
    restored = Trigger.from_dict(trigger.to_dict())
    assert isinstance(restored, DateTrigger)
    assert restored.run_date == trigger.run_date


def test_combining_trigger_roundtrip():
    trigger = AndTrigger(
        [
            CronTrigger(hour=10, minute=30),
            CronTrigger(hour=14, minute=0),
        ]
    )
    restored = Trigger.from_dict(trigger.to_dict())
    assert isinstance(restored, AndTrigger)
    assert len(restored.triggers) == 2
    assert all(isinstance(t, CronTrigger) for t in restored.triggers)


def test_or_trigger_explicit_signature():
    trigger = OrTrigger([IntervalTrigger(seconds=60)])
    assert len(trigger.triggers) == 1
