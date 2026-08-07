from typing import Optional, Any, Dict, Mapping
from datetime import datetime, tzinfo
from tzlocal import get_localzone

from pydantic import (
    Field, ConfigDict, model_validator, field_serializer
)

from schedflow.triggers.base import BaseTrigger, TriggerBaseConfigModel
from schedflow.utils import astimezone, datetime_repr, convert_to_datetime


class DateTriggerModel(TriggerBaseConfigModel):
    run_date: Optional[datetime|str] = Field(default=None, description="执行时间")
    timezone: Optional[tzinfo|str] = Field(default=None, description="计算所用的时区")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "run_date": "2024-09-17 09:00:00"
            }
        }
    )

    @field_serializer('timezone')
    def serialize_tz(self, tz: tzinfo, _info) -> str:
        return str(tz)

    @model_validator(mode='before')
    @classmethod
    def validate_date_trigger(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """模型前置处理器：处理时区和日期"""
        effective_tz = astimezone(data.get('timezone')) or get_localzone()
        data['timezone'] = effective_tz
        if data.get("run_date"):
            data['run_date'] = convert_to_datetime(data.get("run_date"), effective_tz)
        else:
            data['run_date'] = datetime.now(effective_tz)
        
        return data


class DateTrigger(BaseTrigger):
    """
    Triggers once on the given datetime. If ``run_date`` is left empty, current time is used.

    :param datetime|str run_date: the date/time to run the job at
    :param datetime.tzinfo|str timezone: time zone for ``run_date`` if it doesn't have one already
    """

    __slots__ = ("run_date", "timezone")
    _trigger_type = "date"
    _pydantic_model_cls = DateTriggerModel

    def __init__(self, run_date=None, *, timezone=None):
        super().__init__(None, run_date=run_date, timezone=timezone)

    def get_next_fire_time(self, previous_fire_time, now):
        return self.run_date if previous_fire_time is None else None

    def __str__(self):
        return f"date[{datetime_repr(self.run_date)}]"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} (run_date='{datetime_repr(self.run_date)}')>"
        )
