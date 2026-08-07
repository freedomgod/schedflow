"""Static trigger registry tests (replaces entry-point discovery)."""

import pytest

from schedflow.triggers.base import Trigger
from schedflow.triggers.registry import TRIGGER_PLUGINS


def test_trigger_plugin_set_is_stable() -> None:
    assert set(TRIGGER_PLUGINS) == {
        "calendarinterval",
        "date",
        "interval",
        "cron",
        "and",
        "or",
    }


def test_trigger_from_dict_uses_registry() -> None:
    trigger = Trigger.from_dict({"type": "interval", "args": {"seconds": 60}})
    assert trigger.__class__.__name__ == "IntervalTrigger"


def test_trigger_from_dict_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown trigger type 'nope'"):
        Trigger.from_dict({"type": "nope", "args": {}})


def test_get_trigger_cls_uses_registry() -> None:
    from schedflow.triggers.cron import CronTrigger

    assert Trigger.get_trigger_cls("cron") is CronTrigger


def test_get_trigger_cls_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown trigger type 'nope'"):
        Trigger.get_trigger_cls("nope")
