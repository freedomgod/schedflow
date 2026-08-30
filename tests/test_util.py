import os
import platform
import sys
from datetime import UTC, date, datetime, timedelta, tzinfo
from functools import partial, wraps
from types import ModuleType
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import pytz

from schedflow.utils import (
    CustomTypeID,
    asbool,
    asint,
    astimezone,
    check_callable_args,
    convert_to_date,
    convert_to_datetime,
    datetime_ceil,
    datetime_repr,
    datetime_to_string,
    datetime_to_utc_timestamp,
    get_callable_name,
    iscoroutinefunction_partial,
    localize,
    maybe_ref,
    normalize,
    obj_to_ref,
    ref_to_obj,
    timedelta_seconds,
    timezone_repr,
    undefined,
    utc_timestamp_to_datetime,
)


class DummyClass:
    def meth(self):
        pass

    @staticmethod
    def staticmeth():
        pass

    @classmethod
    def classmeth(cls):
        pass

    def __call__(self):
        pass

    class InnerDummyClass:
        @classmethod
        def innerclassmeth(cls):
            pass


class InheritedDummyClass(DummyClass):
    pass


class TestAsint:
    @pytest.mark.parametrize("value", ["5s", "shplse"], ids=["digit first", "text"])
    def test_invalid_value(self, value):
        with pytest.raises(ValueError):
            asint(value)

    def test_number(self):
        assert asint("539") == 539

    def test_none(self):
        assert asint(None) is None


class TestAsbool:
    @pytest.mark.parametrize(
        "value",
        [" True", "true ", "Yes", " yes ", "1  ", True],
        ids=[
            "capital true",
            "lowercase true",
            "capital yes",
            "lowercase yes",
            "one",
            "True",
        ],
    )
    def test_true(self, value):
        assert asbool(value) is True

    @pytest.mark.parametrize(
        "value",
        [" False", "false ", "No", " no ", "0  ", False],
        ids=[
            "capital",
            "lowercase false",
            "capital no",
            "lowercase no",
            "zero",
            "False",
        ],
    )
    def test_false(self, value):
        assert asbool(value) is False

    def test_bad_value(self):
        with pytest.raises(ValueError):
            asbool("yep")


class TestAstimezone:
    def test_str(self):
        value = astimezone("Europe/Helsinki")
        assert isinstance(value, tzinfo)

    def test_pytz(self):
        tz = pytz.timezone("Europe/Helsinki")
        assert astimezone(tz) == ZoneInfo(key="Europe/Helsinki")

    def test_none(self):
        assert astimezone(None) is None

    def test_bad_timezone_type(self):
        with pytest.raises(
            NotImplementedError,
            match=r"(a )?tzinfo subclass must (implement|override) tzname\(\)",
        ):
            astimezone(tzinfo())

    def test_bad_local_timezone(self):
        zone = Mock(tzinfo, localize=None, normalize=None, tzname=lambda dt: "local")
        with pytest.raises(ValueError) as exc:
            astimezone(zone)
        assert "Unable to determine the name of the local timezone" in str(exc.value)

    def test_bad_value(self):
        with pytest.raises(TypeError) as exc:
            astimezone(4)
        assert "Expected tzinfo, got int instead" in str(exc.value)


class TestConvertToDatetime:
    @pytest.mark.parametrize(
        "input,expected",
        [
            (None, None),
            (date(2009, 8, 1), datetime(2009, 8, 1)),
            (datetime(2009, 8, 1, 5, 6, 12), datetime(2009, 8, 1, 5, 6, 12)),
            ("2009-8-1", datetime(2009, 8, 1)),
            ("2009-8-1 5:16:12", datetime(2009, 8, 1, 5, 16, 12)),
            ("2009-8-1T5:16:12Z", datetime(2009, 8, 1, 5, 16, 12, tzinfo=pytz.utc)),
            (
                "2009-8-1T5:16:12+02:30",
                pytz.FixedOffset(150).localize(datetime(2009, 8, 1, 5, 16, 12)),
            ),
            (
                "2009-8-1T5:16:12-05:30",
                pytz.FixedOffset(-330).localize(datetime(2009, 8, 1, 5, 16, 12)),
            ),
            (
                pytz.FixedOffset(-60).localize(datetime(2009, 8, 1)),
                pytz.FixedOffset(-60).localize(datetime(2009, 8, 1)),
            ),
        ],
        ids=[
            "None",
            "date",
            "datetime",
            "date as text",
            "datetime as text",
            "utc",
            "tzoffset",
            "negtzoffset",
            "existing tzinfo",
        ],
    )
    def test_date(self, timezone, input, expected):
        returned = convert_to_datetime(input, timezone)
        if expected is not None:
            assert isinstance(returned, datetime)
            expected = localize(expected, timezone) if not expected.tzinfo else expected

        assert returned == expected

    def test_invalid_input_type(self, timezone):
        with pytest.raises(TypeError) as exc:
            convert_to_datetime(92123, timezone)
        assert "Unsupported input type" in str(exc.value) and "int" in str(exc.value)

    def test_invalid_input_value(self, timezone):
        with pytest.raises(ValueError) as exc:
            convert_to_datetime("19700-12-1", timezone)
        assert str(exc.value) == "Invalid date string"

    def test_missing_timezone(self):
        with pytest.raises(ValueError) as exc:
            convert_to_datetime("2009-8-1", None)
        assert "missing timezone information" in str(exc.value).lower()

    def test_text_timezone(self):
        returned = convert_to_datetime("2009-8-1", pytz.utc)
        assert returned == datetime(2009, 8, 1, tzinfo=pytz.utc)


def test_datetime_to_utc_timestamp(timezone):
    dt = localize(datetime(2014, 3, 12, 5, 40, 13, 254012), timezone)
    timestamp = datetime_to_utc_timestamp(dt)
    dt2 = utc_timestamp_to_datetime(timestamp)
    assert dt2 == dt


@pytest.mark.parametrize(
    "input,expected",
    [
        (datetime(2009, 4, 7, 2, 10, 16, 4000), datetime(2009, 4, 7, 2, 10, 17)),
        (datetime(2009, 4, 7, 2, 10, 16), datetime(2009, 4, 7, 2, 10, 16)),
    ],
    ids=["milliseconds", "exact"],
)
def test_datetime_ceil(input, expected):
    assert datetime_ceil(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        (None, "None"),
        (
            pytz.timezone("Europe/Helsinki").localize(datetime(2014, 5, 30, 7, 12, 20)),
            "2014-05-30 07:12:20 EEST",
        ),
    ],
    ids=["None", "datetime+tzinfo"],
)
def test_datetime_repr(input, expected):
    assert datetime_repr(input) == expected


class TestGetCallableName:
    @pytest.mark.parametrize(
        "input,expected",
        [
            (asint, "asint"),
            (os.getpid, "getpid"),
            (DummyClass.staticmeth, "DummyClass.staticmeth"),
            (DummyClass.classmeth, "DummyClass.classmeth"),
            (DummyClass.meth, "DummyClass.meth"),
            (DummyClass().meth, "DummyClass.meth"),
            (DummyClass, "DummyClass"),
            (DummyClass(), "DummyClass"),
            (InheritedDummyClass.classmeth, "InheritedDummyClass.classmeth"),
            (
                DummyClass.InnerDummyClass.innerclassmeth,
                "DummyClass.InnerDummyClass.innerclassmeth",
            ),
        ],
        ids=[
            "function",
            "builtin",
            "static method",
            "class method",
            "unbounded method",
            "bounded method",
            "class",
            "instance",
            "class method in inherited",
            "inner class method",
        ],
    )
    def test_inputs(self, input, expected):
        assert get_callable_name(input) == expected

    def test_bad_input(self):
        with pytest.raises(TypeError):
            get_callable_name(object())


class TestObjToRef:
    class InnerInheritedDummy(DummyClass):
        pass

    InnerInheritedDummy.__module__ = "foo"

    @pytest.mark.parametrize(
        "obj, error",
        [
            (partial(DummyClass.meth), "Cannot create a reference to a partial()"),
            (lambda: None, "Cannot create a reference to a lambda"),
        ],
        ids=["partial", "lambda"],
    )
    def test_errors(self, obj, error):
        with pytest.raises(ValueError) as exc:
            obj_to_ref(obj)
        assert str(exc.value) == error

    @pytest.mark.skipif(
        sys.version_info[:2] < (3, 3), reason="Requires __qualname__ (Python 3.3+)"
    )
    def test_nested_function_error(self):
        def nested():
            pass

        with pytest.raises(ValueError) as exc:
            obj_to_ref(nested)
        assert str(exc.value) == "Cannot create a reference to a nested function"

    @pytest.mark.parametrize(
        "input,expected",
        [
            (DummyClass.meth, "tests.test_util:DummyClass.meth"),
            (DummyClass.classmeth, "tests.test_util:DummyClass.classmeth"),
            pytest.param(
                DummyClass.InnerDummyClass.innerclassmeth,
                "tests.test_util:DummyClass.InnerDummyClass.innerclassmeth",
                marks=[
                    pytest.mark.skipif(
                        sys.version_info < (3, 3),
                        reason="Requires __qualname__ (Python 3.3+)",
                    )
                ],
            ),
            pytest.param(
                DummyClass.staticmeth,
                "tests.test_util:DummyClass.staticmeth",
                marks=[
                    pytest.mark.skipif(
                        sys.version_info < (3, 3),
                        reason="Requires __qualname__ (Python 3.3+)",
                    )
                ],
            ),
            (timedelta, "datetime:timedelta"),
        ],
        ids=[
            "class method",
            "inner class method",
            "static method",
            "inherited class method",
            "timedelta",
        ],
    )
    def test_valid_refs(self, input, expected):
        assert obj_to_ref(input) == expected

    def test_inherited_classmethod(self):
        assert obj_to_ref(TestObjToRef.InnerInheritedDummy.classmeth) == (
            "foo:TestObjToRef.InnerInheritedDummy.classmeth"
        )


class TestRefToObj:
    def test_valid_ref(self):
        from logging.handlers import RotatingFileHandler

        assert ref_to_obj("logging.handlers:RotatingFileHandler") is RotatingFileHandler

    def test_complex_path(self):
        pkg1 = ModuleType("pkg1")
        pkg1.pkg2 = "blah"
        pkg2 = ModuleType("pkg1.pkg2")
        pkg2.varname = "test"
        sys.modules["pkg1"] = pkg1
        sys.modules["pkg1.pkg2"] = pkg2
        assert ref_to_obj("pkg1.pkg2:varname") == "test"

    @pytest.mark.parametrize(
        "input,error",
        [(object(), TypeError), ("module", ValueError), ("module:blah", LookupError)],
        ids=["raw object", "module", "module attribute"],
    )
    def test_lookup_error(self, input, error):
        with pytest.raises(error):
            ref_to_obj(input)


@pytest.mark.parametrize(
    "input,expected",
    [("datetime:timedelta", timedelta), (timedelta, timedelta)],
    ids=["textref", "direct"],
)
def test_maybe_ref(input, expected):
    assert maybe_ref(input) == expected


class TestCheckCallableArgs:
    def test_invalid_callable_args(self):
        """
        Tests that attempting to create a job with an invalid number of arguments raises an
        exception.

        """
        with pytest.raises(ValueError) as exc:
            check_callable_args(lambda x: None, [1, 2], {})
        assert str(exc.value) == (
            "The list of positional arguments is longer than the target callable can handle "
            "(allowed: 1, given in args: 2)"
        )

    def test_invalid_callable_kwargs(self):
        """
        Tests that attempting to schedule a job with unmatched keyword arguments raises an
        exception.

        """
        with pytest.raises(ValueError) as exc:
            check_callable_args(lambda x: None, [], {"x": 0, "y": 1})
        assert str(exc.value) == (
            "The target callable does not accept the following keyword arguments: y"
        )

    def test_missing_callable_args(self):
        """Tests that attempting to schedule a job with missing arguments raises an exception."""
        with pytest.raises(ValueError) as exc:
            check_callable_args(lambda x, y, z: None, [1], {"y": 0})
        assert str(exc.value) == "The following arguments have not been supplied: z"

    def test_default_args(self):
        """Tests that default values for arguments are properly taken into account."""
        with pytest.raises(ValueError) as exc:
            check_callable_args(lambda x, y, z=1: None, [1], {})
        assert str(exc.value) == "The following arguments have not been supplied: y"

    def test_conflicting_callable_args(self):
        """
        Tests that attempting to schedule a job where the combination of args and kwargs are in
        conflict raises an exception.

        """
        with pytest.raises(ValueError) as exc:
            check_callable_args(lambda x, y: None, [1, 2], {"y": 1})
        assert (
            str(exc.value)
            == "The following arguments are supplied in both args and kwargs: y"
        )

    def test_signature_positional_only(self):
        """Tests that a function where signature() fails is accepted."""
        check_callable_args(object().__setattr__, ("blah", 1), {})

    @pytest.mark.skipif(
        platform.python_implementation() == "PyPy",
        reason="PyPy does not expose signatures of builtins",
    )
    def test_positional_only_args(self):
        """
        Tests that an attempt to use keyword arguments for positional-only arguments raises an
        exception.

        """
        with pytest.raises(ValueError) as exc:
            check_callable_args(object.__setattr__, ["blah"], {"value": 1})
        assert str(exc.value) == (
            "The following arguments cannot be given as keyword arguments: value"
        )

    def test_unfulfilled_kwargs(self):
        """
        Tests that attempting to schedule a job where not all keyword-only arguments are fulfilled
        raises an exception.

        """
        func = eval("lambda x, *, y, z=1: None")
        with pytest.raises(ValueError) as exc:
            check_callable_args(func, [1], {})
        assert str(exc.value) == (
            "The following keyword-only arguments have not been supplied in "
            "kwargs: y"
        )

    def test_wrapped_func(self):
        """
        Test that a wrapped function can be scheduled even if it cannot accept the arguments given
        in add_job() if the wrapper can.
        """

        def func():
            pass

        @wraps(func)
        def wrapper(arg):
            func()

        check_callable_args(wrapper, (1,), {})


class TestIsCoroutineFunctionPartial:
    @staticmethod
    def not_a_coro(x):
        pass

    @staticmethod
    async def a_coro(x):
        pass

    def test_non_coro(self):
        assert not iscoroutinefunction_partial(self.not_a_coro)

    def test_coro(self):
        assert iscoroutinefunction_partial(self.a_coro)

    def test_coro_partial(self):
        assert iscoroutinefunction_partial(partial(self.a_coro, 1))


class TestNormalize:
    def test_normalize_preserves_time(self):
        dt = datetime(2023, 10, 1, 12, 0, 0, tzinfo=UTC)
        result = normalize(dt)
        assert result == dt

    def test_normalize_with_zoneinfo(self):
        tz = ZoneInfo("Europe/Berlin")
        dt = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz)
        result = normalize(dt)
        assert result.tzinfo == tz
        assert result.timestamp() == dt.timestamp()


class TestConvertToDate:
    def test_from_string(self):
        result = convert_to_date("2023-10-01")
        assert result == date(2023, 10, 1)

    def test_from_date_object(self):
        d = date(2023, 5, 15)
        result = convert_to_date(d)
        assert result is d


class TestDatetimeToString:
    def test_none_returns_none(self):
        assert datetime_to_string(None) is None

    def test_naive_datetime(self):
        dt = datetime(2023, 10, 1, 12, 0, 0)
        result = datetime_to_string(dt)
        assert result == "2023-10-01T12:00:00"

    def test_utc_timezone_becomes_z(self):
        dt = datetime(2023, 10, 1, 12, 0, 0, tzinfo=UTC)
        result = datetime_to_string(dt)
        assert result.endswith("Z")

    def test_offset_timezone(self):
        tz = ZoneInfo("Europe/Berlin")
        dt = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz)
        result = datetime_to_string(dt)
        assert "+02:00" in result or "+01:00" in result


class TestTimezoneRepr:
    def test_zoneinfo_returns_key(self):
        tz = ZoneInfo("Europe/Helsinki")
        assert timezone_repr(tz) == "Europe/Helsinki"

    def test_other_tzinfo_returns_repr(self):
        result = timezone_repr(UTC)
        assert "utc" in result.lower() or "timezone" in result


class TestTimedeltaSeconds:
    def test_positive_delta(self):
        delta = timedelta(days=1, hours=2, minutes=3, seconds=4, milliseconds=500)
        result = timedelta_seconds(delta)
        expected = 86400 + 7200 + 180 + 4 + 0.5  # 1 day + 2h + 3m + 4s + 500ms
        assert result == expected

    def test_zero_delta(self):
        assert timedelta_seconds(timedelta()) == 0.0


class TestUndefined:
    def test_undefined_is_falsy(self):
        assert not undefined

    def test_undefined_repr(self):
        assert repr(undefined) == "<undefined>"

    def test_undefined_bool(self):
        assert bool(undefined) is False


class TestCustomTypeID:
    def test_init_with_prefix(self):
        tid = CustomTypeID(prefix="test")
        assert tid.prefix == "test"

    def test_full_str(self):
        result = CustomTypeID.full_str(prefix="job")
        assert result.startswith("job_")

    def test_partial_prefix_returns_partial(self):
        result = CustomTypeID.partial_prefix("task")
        assert callable(result)
        tid_str = result()
        assert tid_str.startswith("task_")

    def test_repr(self):
        tid = CustomTypeID(prefix="flow")
        r = repr(tid)
        assert "CustomTypeID" in r
        assert "flow_" in r

    def test_default_init(self):
        tid = CustomTypeID()
        assert tid.prefix == ""
