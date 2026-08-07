"""Shared base model mixin for SchedFlow.

Provides ``BaseModelMixin`` — a proxy pattern that wraps a Pydantic model
while exposing its fields via ``__getattr__`` for transparent attribute
access. Kept in ``utils`` because it is used by the shared ``triggers``
subsystem and historically by the (now removed) ``models`` package.
"""

from __future__ import annotations

from pydantic import (
    BaseModel,
    SerializationInfo,
)


class BaseModelMixin:
    """Base class for all models that require automatic Pydantic model initialization.

    Provides a bridge between regular Python objects (with ``__slots__`` and pickle
    support) and Pydantic v2 models (with validation and serialization). Subclasses
    must set ``_pydantic_model_cls`` to the corresponding Pydantic model class.
    """

    __slots__ = ("_model",)
    _pydantic_model_cls: type[BaseModel] | None = None

    def __new__(cls, *args, **kwargs):
        if cls._pydantic_model_cls is None:
            raise NotImplementedError(
                f"{cls.__name__} must define '_pydantic_model_cls' class variable"
            )
        instance = super().__new__(cls)
        object.__setattr__(instance, "_model", None)
        return instance

    def __init__(self, model=None, **kwargs):
        if model:
            if isinstance(model, self._pydantic_model_cls):
                self._model = model
            elif isinstance(model, dict):
                self._model = self._pydantic_model_cls(**model)
            else:
                raise ValueError(
                    f"model must be dict or {self._pydantic_model_cls.__name__}"
                )
        else:
            self._model = self._pydantic_model_cls(**kwargs)

    def model_dump(self, info: dict | SerializationInfo = None, **kwargs):
        if info is None:
            return self._model.model_dump(**kwargs)
        if isinstance(info, dict):
            return self._model.model_dump(**info)
        return self._model.model_dump(
            mode=info.mode,
            by_alias=info.by_alias,
            include=info.include,
            exclude=info.exclude,
            context=info.context,
            exclude_unset=info.exclude_unset,
            exclude_defaults=info.exclude_defaults,
            exclude_none=info.exclude_none,
            round_trip=info.round_trip,
            serialize_as_any=info.serialize_as_any,
        )

    def __getattr__(self, name):
        return getattr(self._model, name)

    def __setattr__(self, name, value):
        if name == "_model":
            if isinstance(value, self._pydantic_model_cls):
                super().__setattr__(name, value)
            else:
                super().__setattr__(name, self._pydantic_model_cls(**value))
        elif name.startswith("_"):
            super().__setattr__(name, value)
        else:
            object.__setattr__(self._model, name, value)

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        return self._model.model_dump(mode="json")

    def __setstate__(self, state):
        object.__setattr__(self, "_model", self._pydantic_model_cls(**state))

    def __repr__(self):
        return repr(self._model)
