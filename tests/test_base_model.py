"""Tests for the BaseModelMixin class."""

import pickle

import pytest
from pydantic import BaseModel, ConfigDict, Field

from schedflow.utils.base_model import BaseModelMixin


class _SimplePydanticModel(BaseModel):
    name: str = "default_name"
    value: int = 0
    model_config = ConfigDict(extra="forbid")


class SimpleModel(BaseModelMixin):
    __slots__ = ("name", "value")
    _pydantic_model_cls = _SimplePydanticModel


class _ComplexPydanticModel(BaseModel):
    name: str = "default_name"
    value: int = 0
    tags: list = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ComplexModel(BaseModelMixin):
    __slots__ = ("name", "tags", "value")
    _pydantic_model_cls = _ComplexPydanticModel


class TestBaseModelMixinInit:
    def test_init_with_no_args_uses_defaults(self):
        m = SimpleModel()
        assert m.name == "default_name"
        assert m.value == 0

    def test_init_with_kwargs(self):
        m = SimpleModel(name="test", value=42)
        assert m.name == "test"
        assert m.value == 42

    def test_init_with_dict_model(self):
        m = SimpleModel(model={"name": "from_dict", "value": 99})
        assert m.name == "from_dict"
        assert m.value == 99

    def test_init_with_pydantic_model_instance(self):
        pydantic_model = _SimplePydanticModel(name="from_instance", value=77)
        m = SimpleModel(model=pydantic_model)
        assert m.name == "from_instance"
        assert m.value == 77

    def test_init_with_invalid_model_type_raises(self):
        with pytest.raises(ValueError, match="model must be dict or _SimplePydanticModel"):
            SimpleModel(model=123)

    def test_init_with_list_factory_default(self):
        m = ComplexModel(tags=["a", "b"])
        assert m.tags == ["a", "b"]

    def test_subclass_must_define_pydantic_model_cls(self):
        class BadModel(BaseModelMixin):
            pass

        with pytest.raises(NotImplementedError, match="must define '_pydantic_model_cls'"):
            BadModel()


class TestBaseModelMixinGetattrSetattr:
    def test_getattr_delegates_to_model(self):
        m = SimpleModel(name="proxy_test", value=10)
        assert m.name == "proxy_test"
        assert m.value == 10

    def test_setattr_delegates_to_model(self):
        m = SimpleModel(name="original", value=1)
        m.name = "updated"
        m.value = 100
        assert m.name == "updated"
        assert m.value == 100

    def test_setattr_model_field_delegates_to_model(self):
        m = SimpleModel(name="original", value=1)
        # Setting a field that exists in _pydantic_model_cls delegates to the pydantic model
        m.name = "updated"
        m.value = 100
        assert m._model.name == "updated"
        assert m._model.value == 100

    def test_getattr_raises_for_unknown_field(self):
        m = SimpleModel()
        with pytest.raises(AttributeError):
            _ = m.nonexistent_field


class TestBaseModelMixinModelDump:
    def test_model_dump_no_args(self):
        m = SimpleModel(name="dump_test", value=55)
        result = m.model_dump()
        assert result == {"name": "dump_test", "value": 55}

    def test_model_dump_with_dict_info(self):
        m = SimpleModel(name="dump_test", value=55)
        result = m.model_dump({"mode": "json"})
        assert result == {"name": "dump_test", "value": 55}

    def test_model_dump_with_serialization_info(self):
        m = SimpleModel(name="dump_test", value=55)
        # Test that model_dump handles info dict with mode key correctly
        result = m.model_dump({"mode": "json", "exclude": {"value"}})
        assert result == {"name": "dump_test"}

    def test_model_dump_exclude(self):
        m = SimpleModel(name="test", value=42)
        result = m.model_dump(exclude={"value"})
        assert result == {"name": "test"}


class TestBaseModelMixinPickle:
    def test_pickle_roundtrip(self):
        m = SimpleModel(name="pickle_test", value=123)
        data = pickle.dumps(m)
        restored = pickle.loads(data)
        assert restored.name == "pickle_test"
        assert restored.value == 123

    def test_pickle_roundtrip_with_complex_model(self):
        m = ComplexModel(name="complex", value=7, tags=["x", "y"])
        data = pickle.dumps(m)
        restored = pickle.loads(data)
        assert restored.name == "complex"
        assert restored.value == 7
        assert restored.tags == ["x", "y"]


class TestBaseModelMixinRepr:
    def test_repr(self):
        m = SimpleModel(name="repr_test", value=99)
        r = repr(m)
        assert "repr_test" in r
        assert "99" in r

    def test_str(self):
        m = SimpleModel(name="str_test", value=88)
        s = str(m)
        assert "str_test" in s
        assert "88" in s
