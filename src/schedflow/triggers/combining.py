from typing import Optional, Mapping
from pydantic import (
    Field, ConfigDict
)

from schedflow.triggers.base import (
    BaseTrigger,
    Trigger,
    TriggerBaseConfigModel,
    TriggerType,
)
from schedflow.utils import obj_to_ref, ref_to_obj



class CombiningTriggerModel(TriggerBaseConfigModel):
    triggers: Optional[list[TriggerType]] = Field(default=None, description="触发器列表")
    jitter: Optional[int] = Field(default=None, description="任务最多延迟执行的时间")


class BaseCombiningTrigger(BaseTrigger):
    __slots__ = ("triggers", "jitter")
    _pydantic_model_cls = CombiningTriggerModel

    def __init__(self, triggers=None, *, jitter=None):
        super().__init__(None, triggers=triggers, jitter=jitter)

    def to_dict(self) -> dict:
        return {
            "type": self._trigger_type,
            "args": {
                "triggers": [trigger.to_dict() for trigger in self.triggers],
                "jitter": self.jitter,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BaseCombiningTrigger":
        args = data.get("args", {})
        triggers = [Trigger.from_dict(item) for item in args.get("triggers", [])]
        return cls(triggers=triggers, jitter=args.get("jitter"))
    
    def __repr__(self):
        return "<{}({}{})>".format(
            self.__class__.__name__,
            self.triggers,
            f", jitter={self.jitter}" if self.jitter else "",
        )


class AndTrigger(BaseCombiningTrigger):
    """
    Always returns the earliest next fire time that all the given triggers can agree on.
    The trigger is considered to be finished when any of the given triggers has finished its
    schedule.

    Trigger alias: ``and``

    .. warning:: This trigger should only be used to combine triggers that fire on
        specific times of day, such as
        :class:`~schedflow.triggers.cron.CronTrigger` and
        class:`~schedflow.triggers.calendarinterval.CalendarIntervalTrigger`.
        Attempting to use it with
        :class:`~schedflow.triggers.interval.IntervalTrigger` will likely result in
        the scheduler hanging as it tries to find a fire time that matches exactly
        between fire times produced by all the given triggers.

    :param list triggers: triggers to combine
    :param int|None jitter: delay the job execution by ``jitter`` seconds at most
    """

    __slots__ = ()
    _trigger_type = "and"

    def get_next_fire_time(self, previous_fire_time, now):
        while True:
            fire_times = [
                trigger.get_next_fire_time(previous_fire_time, now)
                for trigger in self.triggers
            ]
            if None in fire_times:
                return None
            elif min(fire_times) == max(fire_times):
                return self._apply_jitter(fire_times[0], self.jitter, now)
            else:
                now = max(fire_times)

    def __str__(self):
        return "and[{}]".format(", ".join(str(trigger) for trigger in self.triggers))


class OrTrigger(BaseCombiningTrigger):
    """
    Always returns the earliest next fire time produced by any of the given triggers.
    The trigger is considered finished when all the given triggers have finished their schedules.

    Trigger alias: ``or``

    :param list triggers: triggers to combine
    :param int|None jitter: delay the job execution by ``jitter`` seconds at most

    .. note:: Triggers that depends on the previous fire time, such as the interval trigger, may
        seem to behave strangely since they are always passed the previous fire time produced by
        any of the given triggers.
    """

    __slots__ = ()
    _trigger_type = "or"

    def get_next_fire_time(self, previous_fire_time, now):
        fire_times = [
            trigger.get_next_fire_time(previous_fire_time, now)
            for trigger in self.triggers
        ]
        fire_times = [fire_time for fire_time in fire_times if fire_time is not None]
        if fire_times:
            return self._apply_jitter(min(fire_times), self.jitter, now)
        else:
            return None

    def __str__(self):
        return "or[{}]".format(", ".join(str(trigger) for trigger in self.triggers))

