"""Combination searches must terminate when periodic phases never agree."""

from datetime import UTC, datetime, timedelta

import pytest

from schedflow.triggers.combining import AndTrigger
from schedflow.triggers.interval import IntervalTrigger


def test_opposing_interval_phases_raise_instead_of_searching_forever(monkeypatch):
    start = datetime(2026, 10, 11, tzinfo=UTC)
    trigger = AndTrigger(
        triggers=[
            IntervalTrigger(seconds=1, start_date=start, timezone=UTC),
            IntervalTrigger(
                seconds=1,
                start_date=start + timedelta(microseconds=500000),
                timezone=UTC,
            ),
        ]
    )
    original = IntervalTrigger.get_next_fire_time
    calls = 0

    def guarded(self, previous, now):
        nonlocal calls
        calls += 1
        # Prevent a broken implementation from hanging the test process.
        if calls > 20002:
            raise AssertionError("AndTrigger intersection search remained unbounded")
        return original(self, previous, now)

    monkeypatch.setattr(IntervalTrigger, "get_next_fire_time", guarded)
    with pytest.raises(ValueError, match=r"intersection.*limit"):
        trigger.get_next_fire_time(None, start)
    assert calls <= 2 * trigger.MAX_ITERATIONS


def test_compatible_intervals_keep_their_existing_fire_time():
    start = datetime(2026, 10, 11, tzinfo=UTC)
    trigger = AndTrigger(
        triggers=[
            IntervalTrigger(seconds=1, start_date=start, timezone=UTC),
            IntervalTrigger(seconds=2, start_date=start, timezone=UTC),
        ]
    )
    assert trigger.get_next_fire_time(
        None, start + timedelta(seconds=1)
    ) == start + timedelta(seconds=2)
    encoded = trigger.to_dict()
    assert set(encoded["args"]) == {"triggers", "jitter"}
