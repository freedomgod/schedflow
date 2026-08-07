import random
from datetime import datetime, timedelta
from math import ceil
from typing import Optional, Mapping, Dict, Any
from tzlocal import get_localzone
from datetime import datetime, tzinfo

from pydantic import (
    Field, ConfigDict, model_validator, field_serializer
)

from schedflow.triggers.base import BaseTrigger, TriggerBaseConfigModel
from schedflow.utils import (
    astimezone,
    convert_to_datetime,
    datetime_repr,
)



class IntervalTriggerModel(TriggerBaseConfigModel):
    weeks: Optional[int] = Field(default=0, description="等待的周数")
    days: Optional[int] = Field(default=0, description="等待的天数")
    hours: Optional[int] = Field(default=0, description="等待的小时数")
    minutes: Optional[int] = Field(default=0, description="等待的小时数")
    seconds: Optional[int] = Field(default=0, description="等待的秒数")
    start_date: Optional[datetime|str] = Field(default=None, description="开始计算运行时间的起始时间")
    end_date: Optional[datetime|str] = Field(default=None, description="最后可能结束触发的运行时间")
    timezone: Optional[tzinfo|str] = Field(default=None, description="计算所用的时区")
    jitter: Optional[int] = Field(default=None, description="任务最多延迟执行的时间")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "days": 0,
                "hours": 1,
                "minutes": 2,
                "seconds": 5,
                "start_date": "2024-09-17 09:00:00",
                "end_date": "2024-09-27 09:00:00",
                "jitter": 10
            }
        }
    )

    @field_serializer('timezone')
    def serialize_tz(self, tz: tzinfo, _info) -> str:
        return str(tz)

    @model_validator(mode='before')
    @classmethod
    def interval_model_validator(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        timezone = data.get('timezone')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if timezone:
            data['timezone'] = astimezone(timezone)
        elif isinstance(start_date, datetime) and start_date.tzinfo:
            data['timezone'] = astimezone(start_date.tzinfo)
        elif isinstance(end_date, datetime) and end_date.tzinfo:
            data['timezone'] = astimezone(end_date.tzinfo)
        else:
            data['timezone'] = get_localzone()

        interval = timedelta(
            weeks=data.get('weeks', 0),
            days=data.get('days', 0),
            hours=data.get('hours', 0),
            minutes=data.get('minutes', 0),
            seconds=data.get('seconds', 0)
        )

        start_date = start_date or (datetime.now(data['timezone']) + interval)
        end_date = data.get('end_date')
        data['start_date'] = convert_to_datetime(start_date, data['timezone'])
        data['end_date'] = convert_to_datetime(end_date, data['timezone'])

        return data


class IntervalTrigger(BaseTrigger):
    """
    Triggers on specified intervals, starting on ``start_date`` if specified, ``datetime.now()`` +
    interval otherwise.

    :param int weeks: number of weeks to wait
    :param int days: number of days to wait
    :param int hours: number of hours to wait
    :param int minutes: number of minutes to wait
    :param int seconds: number of seconds to wait
    :param datetime|str start_date: starting point for the interval calculation
    :param datetime|str end_date: latest possible date/time to trigger on
    :param datetime.tzinfo|str timezone: time zone to use for the date/time calculations
    :param int|None jitter: delay the job execution by ``jitter`` seconds at most
    """

    __slots__ = (
        "weeks", "days", "hours", "minutes", "seconds",
        "start_date", "end_date", "timezone", "jitter",
        "_interval", "_interval_length",
    )
    _trigger_type = "interval"
    _pydantic_model_cls = IntervalTriggerModel


    def __init__(
        self,
        *,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_date=None,
        end_date=None,
        timezone=None,
        jitter: Optional[int] = None,
    ):
        super().__init__(
            None,
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
            jitter=jitter,
        )
        self._init_interval()

    def _init_interval(self):
        self._interval = timedelta(
            weeks=self.weeks, days=self.days, hours=self.hours,
            minutes=self.minutes, seconds=self.seconds
        )
        self._interval_length = self._interval.total_seconds()
        if self._interval_length == 0:
            self._interval = timedelta(seconds=1)
            self._interval_length = 1

    def __setstate__(self, state):
        super().__setstate__(state)
        self._init_interval()

    def get_next_fire_time(self, previous_fire_time, now):
        if previous_fire_time:
            next_fire_time = previous_fire_time.timestamp() + self._interval_length
        elif self.start_date > now:
            next_fire_time = self.start_date.timestamp()
        else:
            timediff = now.timestamp() - self.start_date.timestamp()
            next_interval_num = int(ceil(timediff / self._interval_length))
            next_fire_time = (
                self.start_date.timestamp() + self._interval_length * next_interval_num
            )

        if self.jitter is not None:
            next_fire_time += random.uniform(0, self.jitter)

        if not self.end_date or next_fire_time <= self.end_date.timestamp():
            return datetime.fromtimestamp(next_fire_time, tz=self.timezone)

    def __str__(self):
        return f"interval[{self._interval!s}]"

    def __repr__(self):
        options = [
            f"interval={self._interval!r}",
            f"start_date={datetime_repr(self.start_date)!r}",
        ]
        if self.end_date:
            options.append(f"end_date={datetime_repr(self.end_date)!r}")
        if self.jitter:
            options.append(f"jitter={self.jitter}")

        return "<{} ({}, timezone='{}')>".format(
            self.__class__.__name__,
            ", ".join(options),
            self.timezone,
        )
