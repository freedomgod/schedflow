"""Static trigger registry (replaces entry-point discovery)."""

from __future__ import annotations

from schedflow.triggers.calendarinterval import CalendarIntervalTrigger
from schedflow.triggers.combining import AndTrigger, OrTrigger
from schedflow.triggers.cron import CronTrigger
from schedflow.triggers.date import DateTrigger
from schedflow.triggers.interval import IntervalTrigger

TRIGGER_PLUGINS: dict[str, type] = {
    "calendarinterval": CalendarIntervalTrigger,
    "date": DateTrigger,
    "interval": IntervalTrigger,
    "cron": CronTrigger,
    "and": AndTrigger,
    "or": OrTrigger,
}
