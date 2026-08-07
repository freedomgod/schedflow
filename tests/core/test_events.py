"""Event bus tests."""

import pytest

from schedflow.core.events import EventBus, SchedulerEvent


def test_subscribe_and_publish():
    bus = EventBus()
    seen = []
    bus.subscribe("job.added", seen.append)

    bus.publish(SchedulerEvent("job.added", job_id="j1"))

    assert seen[0].job_id == "j1"


def test_wildcard_subscribe():
    bus = EventBus()
    seen = []
    bus.subscribe("*", lambda event: seen.append(event.kind))

    bus.publish(SchedulerEvent("job.added"))
    bus.publish(SchedulerEvent("job.removed"))

    assert seen == ["job.added", "job.removed"]


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="kind"):
        SchedulerEvent("no.such.kind")


def test_unsubscribe():
    bus = EventBus()
    seen = []
    callback = seen.append
    bus.subscribe("job.added", callback)

    assert bus.unsubscribe("job.added", callback) is True
    bus.publish(SchedulerEvent("job.added"))

    assert seen == []


def test_listener_error_is_isolated():
    bus = EventBus()
    seen = []

    def bad_listener(event):
        raise RuntimeError("boom")

    bus.subscribe("job.added", bad_listener)
    bus.subscribe("job.added", lambda event: seen.append(event.kind))

    bus.publish(SchedulerEvent("job.added"))

    assert seen == ["job.added"]
