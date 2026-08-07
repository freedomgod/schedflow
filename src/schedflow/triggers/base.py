import random
from abc import ABCMeta, abstractmethod
from collections.abc import Mapping
from datetime import timedelta
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    SerializationInfo,
    ValidationError,
)
from pydantic_core import core_schema

from schedflow.exceptions.triggers import TriggerValidationError
from schedflow.utils.base_model import BaseModelMixin


class TriggerEnum(str, Enum):  # noqa: UP042 - keep legacy str() semantics
    # Trigger type constants
    CRON = 'cron'
    DATE = 'date'
    INTERVAL = 'interval'


_TRIGGER_REGISTRY: dict[str, type] = {}


class BaseTrigger(BaseModelMixin, metaclass=ABCMeta):
    """Abstract base class that defines the interface that every trigger must implement."""

    _trigger_type: str
    _pydantic_model_cls: BaseModel

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        trigger_type = getattr(cls, "_trigger_type", None)
        if trigger_type:
            _TRIGGER_REGISTRY[trigger_type] = cls

    def __init__(self, model=None, **kwargs):
        try:
            super().__init__(model, **kwargs)
        except ValidationError as e:
            raise TriggerValidationError(e, self._pydantic_model_cls.__name__)

    @abstractmethod
    def get_next_fire_time(self, previous_fire_time, now):
        """
        Returns the next datetime to fire on, If no such datetime can be calculated, returns
        ``None``.

        :param datetime.datetime previous_fire_time: the previous time the trigger was fired
        :param datetime.datetime now: current datetime
        """

    def _apply_jitter(self, next_fire_time, jitter, now):
        """
        Randomize ``next_fire_time`` by adding a random value (the jitter).

        :param datetime.datetime|None next_fire_time: next fire time without jitter applied. If
            ``None``, returns ``None``.
        :param int|None jitter: maximum number of seconds to add to ``next_fire_time``
            (if ``None`` or ``0``, returns ``next_fire_time``)
        :param datetime.datetime now: current datetime
        :return datetime.datetime|None: next fire time with a jitter.
        """
        if next_fire_time is None or not jitter:
            return next_fire_time

        return next_fire_time + timedelta(seconds=random.uniform(0, jitter))

    @classmethod
    def get_trigger_cls(cls, trigger_type: str):
        from schedflow.triggers.registry import TRIGGER_PLUGINS

        trigger_cls = TRIGGER_PLUGINS.get(trigger_type)
        if trigger_cls is None:
            raise ValueError(
                f"Unknown trigger type {trigger_type!r}; "
                f"available: {sorted(TRIGGER_PLUGINS)}"
            )
        return trigger_cls

    def model_dump(self, info: dict | SerializationInfo = None, **kwargs):
        return {
            'trigger_type': self._trigger_type,
            'trigger_kwargs': super().model_dump(info, **kwargs)
        }

    def to_dict(self) -> dict:
        """Serialize to the JSON contract: ``{"type": ..., "args": {...}}``."""
        return {
            "type": self._trigger_type,
            "args": self._model.model_dump(mode="json"),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BaseTrigger":
        """Rebuild a trigger from ``{"type": ..., "args": {...}}``."""
        trigger_type = data.get("type")
        from schedflow.triggers.registry import TRIGGER_PLUGINS

        trigger_cls = TRIGGER_PLUGINS.get(trigger_type) or _TRIGGER_REGISTRY.get(
            trigger_type
        )
        if trigger_cls is None:
            raise ValueError(
                f"Unknown trigger type {trigger_type!r}; "
                f"available: {sorted(TRIGGER_PLUGINS)}"
            )
        # Subclasses may override deserialization (e.g. combining triggers
        # with nested triggers); otherwise construct with the args dict.
        if trigger_cls.from_dict.__func__ is not BaseTrigger.from_dict.__func__:
            return trigger_cls.from_dict(data)
        return trigger_cls(**data.get("args", {}))

    def __eq__(self, other: BaseModelMixin) -> bool:
        if not isinstance(other, BaseModelMixin):
            return False
        # Compare values of all fields
        return all(
            getattr(self, field) == getattr(other, field)
            # for field, _ in self._pydantic_model_cls.model_fields.keys()
            for field in self.__slots__
        )


class TriggerBaseConfigModel(BaseModel):
    """Base configuration model for trigger validation."""
    model_config = ConfigDict(
        from_attributes = True,
        arbitrary_types_allowed = True,
        extra = "forbid"
    )


class TriggerBaseModel(TriggerBaseConfigModel):
    trigger_type: str | TriggerEnum | None = Field(default=TriggerEnum.CRON, description="触发器类型")
    # trigger_kwargs: Optional[Union[CronTriggerModel, DateTriggerModel, IntervalTriggerModel]] = Field(default=None, description="触发器参数")
    trigger_kwargs: dict | None = Field(default=None, description="触发器参数")


class TriggerType:
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        def validate_trigger(value: Any) -> BaseTrigger:
            if isinstance(value, BaseTrigger):
                return value
            elif isinstance(value, Mapping):
                trig_model = TriggerBaseModel(**value)
                trigger_cls = BaseTrigger.get_trigger_cls(trig_model.trigger_type)
                return trigger_cls(**trig_model.trigger_kwargs)
            elif isinstance(value, TriggerBaseModel):
                trigger_cls = BaseTrigger.get_trigger_cls(value.trigger_type)
                return trigger_cls(**value.trigger_kwargs)
            raise TypeError(f"Failed to create Trigger, value: {value}")

        from_mapping_schema = core_schema.chain_schema(
            [
                core_schema.dict_schema(),
                core_schema.no_info_plain_validator_function(validate_trigger),
            ]
        )

        return core_schema.json_or_python_schema(
            json_schema=from_mapping_schema,
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(BaseTrigger),
                    from_mapping_schema,
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance, info: instance.model_dump(info),
                info_arg=True
            ),
        )


#: Public alias; ``BaseTrigger`` is kept for legacy imports.
Trigger = BaseTrigger


