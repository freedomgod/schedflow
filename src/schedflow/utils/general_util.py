"""General utility functions for SchedFlow.

Provides type conversion, datetime manipulation, timezone handling,
callable reference resolution (obj_to_ref/ref_to_obj), and CustomTypeID
for generating prefixed unique identifiers.
"""

__all__ = (
    "asint",
    "asbool",
    "astimezone",
    "convert_to_date",
    "convert_to_datetime",
    "datetime_to_string",
    "datetime_to_utc_timestamp",
    "utc_timestamp_to_datetime",
    "datetime_ceil",
    "datetime_repr",
    "timezone_repr",
    "get_callable_name",
    "obj_to_ref",
    "ref_to_obj",
    "maybe_ref",
    "check_callable_args",
    "normalize",
    "localize",
    "undefined",
    "CustomTypeID",
    "for_test_callable",
    "iscoroutinefunction_partial",
    "timedelta_seconds",
)

import re
import sys
import pathlib
import importlib
from calendar import timegm
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import partial
from inspect import isbuiltin, isclass, isfunction, ismethod, signature
from typing import Callable, Union, Optional

from typeid import TypeID

if sys.version_info < (3, 14):
    from asyncio import iscoroutinefunction
else:
    from inspect import iscoroutinefunction

if sys.version_info < (3, 9):
    from backports.zoneinfo import ZoneInfo
else:
    from zoneinfo import ZoneInfo


class _Undefined:
    def __nonzero__(self):
        return False

    def __bool__(self):
        return False

    def __repr__(self):
        return "<undefined>"


undefined = (
    _Undefined()
)  #: a unique object that only signifies that no value is defined


def asint(text):
    """
    Safely converts a string to an integer, returning ``None`` if the string is ``None``.

    :type text: str
    :rtype: int

    """
    if text is not None:
        return int(text)


def asbool(obj):
    """
    Interprets an object as a boolean value.

    :rtype: bool

    """
    if isinstance(obj, str):
        obj = obj.strip().lower()
        if obj in ("true", "yes", "on", "y", "t", "1"):
            return True

        if obj in ("false", "no", "off", "n", "f", "0"):
            return False

        raise ValueError(f'Unable to interpret value "{obj}" as boolean')

    return bool(obj)


def astimezone(obj):
    """
    Interprets an object as a timezone.

    :rtype: tzinfo

    """
    if isinstance(obj, str):
        if obj == "UTC":
            return timezone.utc

        return ZoneInfo(obj)

    if isinstance(obj, tzinfo):
        if obj.tzname(None) == "local":
            raise ValueError(
                "Unable to determine the name of the local timezone -- you must "
                "explicitly specify the name of the local timezone. Please refrain "
                "from using timezones like EST to prevent problems with daylight "
                "saving time. Instead, use a locale based timezone name (such as "
                "Europe/Helsinki)."
            )
        elif isinstance(obj, ZoneInfo):
            return obj
        elif hasattr(obj, "zone"):
            # pytz timezones
            if obj.zone:
                return ZoneInfo(obj.zone)

            return timezone(obj._offset)

        return obj

    if obj is not None:
        raise TypeError(f"Expected tzinfo, got {obj.__class__.__name__} instead")


_DATE_REGEX = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[ T](?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    r"(?:\.(?P<microsecond>\d{1,6}))?"
    r"(?P<timezone>Z|[+-]\d\d:\d\d)?)?$"
)


def normalize(dt):
    return datetime.fromtimestamp(dt.timestamp(), dt.tzinfo)


def localize(dt, tzinfo):
    if hasattr(tzinfo, "localize"):  # pytz
        return tzinfo.localize(dt)
    # zoneinfo
    return normalize(dt.replace(tzinfo=tzinfo))


def convert_to_datetime_old(input, tz, arg_name):
    """
    Converts the given object to a timezone aware datetime object.

    If a timezone aware datetime object is passed, it is returned unmodified.
    If a native datetime object is passed, it is given the specified timezone.
    If the input is a string, it is parsed as a datetime with the given timezone.

    Date strings are accepted in three different forms: date only (Y-m-d), date with
    time (Y-m-d H:M:S) or with date+time with microseconds (Y-m-d H:M:S.micro).
    Additionally you can override the time zone by giving a specific offset in the
    format specified by ISO 8601: Z (UTC), +HH:MM or -HH:MM.

    :param str|datetime input: the datetime or string to convert to a timezone aware
        datetime
    :param datetime.tzinfo tz: timezone to interpret ``input`` in
    :param str arg_name: the name of the argument (used in an error message)
    :rtype: datetime

    """
    if input is None:
        return
    elif isinstance(input, datetime):
        datetime_ = input
    elif isinstance(input, date):
        datetime_ = datetime.combine(input, time())
    elif isinstance(input, str):
        m = _DATE_REGEX.match(input)
        if not m:
            raise ValueError("Invalid date string")

        values = m.groupdict()
        tzname = values.pop("timezone")
        if tzname == "Z":
            tz = timezone.utc
        elif tzname:
            hours, minutes = (int(x) for x in tzname[1:].split(":"))
            sign = 1 if tzname[0] == "+" else -1
            tz = timezone(sign * timedelta(hours=hours, minutes=minutes))

        values = {k: int(v or 0) for k, v in values.items()}
        datetime_ = datetime(**values)
    else:
        raise TypeError(f"Unsupported type for {arg_name}: {input.__class__.__name__}")

    if datetime_.tzinfo is not None:
        return datetime_
    if tz is None:
        raise ValueError(
            f'The "tz" argument must be specified if {arg_name} has no timezone information'
        )
    if isinstance(tz, str):
        tz = astimezone(tz)

    return localize(datetime_, tz)


def convert_to_date(obj: str | date) -> date:
    if isinstance(obj, str):
        return date.fromisoformat(obj)
    return obj


def convert_to_datetime(
    input: Union[str, datetime, date, None],
    tz: Optional[tzinfo] = None
) -> Optional[datetime]:
    """
    Convert the input to a timezone-aware datetime object.

    Supported input types:
    1. None → return None
    2. datetime object (timezone-aware or naive)
    3. ISO 8601 formatted datetime string

    Timezone handling rules:
    - If input is a timezone-aware datetime object → return directly
    - If input is a naive datetime object → use the tz parameter to add timezone
    - If input is a string with timezone → preserve the original timezone
    - If input is a string without timezone → use the tz parameter to add timezone

    Note: the tz parameter must be provided when input is a naive datetime or a
    timezone-less string.

    :param input: input value, can be None, a datetime object, or an ISO datetime string
    :param tz: target timezone object (datetime.tzinfo), used to add timezone info
        to naive datetimes
    :return: timezone-aware datetime object, or None (when input is None)
    :raises ValueError: invalid datetime string or missing required timezone info
    :raises TypeError: unsupported input data type

    Examples:
    >>> convert_to_datetime("2023-10-01T12:00:00+08:00")
    datetime(2023, 10, 1, 12, 0, tzinfo=timezone(timedelta(seconds=28800)))

    >>> convert_to_datetime(datetime(2023, 10, 1, 12), timezone.utc)
    datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc)
    """
    # Handle None input
    if input is None:
        return None
    # Handle datetime object input
    elif isinstance(input, datetime):
        dt = input
    elif isinstance(input, date):
        dt = datetime.combine(input, time())
    # Handle string input (ISO 8601 format)
    elif isinstance(input, str):
        try:
            # Parse ISO format string using built-in method
            # Supported format examples:
            #   "2023-10-01"                 → date (no timezone)
            #   "2023-10-01T12:00:00"        → datetime (no timezone)
            #   "2023-10-01T12:00:00+08:00"  → datetime (with timezone)
            #   "2023-10-01T12:00:00Z"       → UTC time
            dt = datetime.fromisoformat(input)
        except ValueError:
            m = _DATE_REGEX.match(input)
            if not m:
                raise ValueError("Invalid date string")

            values = m.groupdict()
            tzname = values.pop("timezone")
            if tzname == "Z":
                tz = timezone.utc
            elif tzname:
                hours, minutes = (int(x) for x in tzname[1:].split(":"))
                sign = 1 if tzname[0] == "+" else -1
                tz = timezone(sign * timedelta(hours=hours, minutes=minutes))

            values = {k: int(v or 0) for k, v in values.items()}
            dt = datetime(**values)
    # Handle unsupported types
    else:
        raise TypeError(f"Unsupported input type: {type(input).__name__}. "
                        "Expected datetime, string or None.")

    # Timezone handling logic
    if dt.tzinfo is None:
        # Naive datetime is missing timezone information
        if tz is None:
            raise ValueError(
                f"Input '{input}' is missing timezone information and "
                "no target timezone (tz) was provided."
            )
        # Add the specified timezone (without time conversion)
        dt = localize(dt, tz)
    return dt


def datetime_to_string(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert a datetime object to an ISO 8601 formatted string.

    Supported scenarios:
    - None value → return None
    - Timezone-aware datetime → preserve timezone info (e.g., "+08:00" or "Z")
    - Naive datetime → output without timezone

    :param dt: the datetime object to convert
    :return: ISO 8601 formatted string, or None (when input is None)

    Examples:
        >>> datetime_to_string(datetime(2023, 10, 1, 12, 0))
        '2023-10-01T12:00:00'

        >>> datetime_to_string(datetime(2023, 10, 1, 12, 0, tzinfo=timezone.utc))
        '2023-10-01T12:00:00Z'
    """
    if dt is None:
        return None
    
    # Base ISO format
    iso_str = dt.isoformat()

    # Handle UTC timezone shorthand (Z)
    if dt.tzinfo == timezone.utc:
        iso_str = iso_str.replace("+00:00", "Z")
    
    return iso_str


def datetime_to_utc_timestamp(timeval):
    """
    Converts a datetime instance to a timestamp.

    :type timeval: datetime
    :rtype: float

    """
    if timeval is not None:
        return timegm(timeval.utctimetuple()) + timeval.microsecond / 1000000


def utc_timestamp_to_datetime(timestamp):
    """
    Converts the given timestamp to a datetime instance.

    :type timestamp: float
    :rtype: datetime

    """
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, timezone.utc)


def timedelta_seconds(delta):
    """
    Converts the given timedelta to seconds.

    :type delta: timedelta
    :rtype: float

    """
    return delta.days * 24 * 60 * 60 + delta.seconds + delta.microseconds / 1000000.0


def datetime_ceil(dateval):
    """
    Rounds the given datetime object upwards.

    :type dateval: datetime

    """
    if dateval.microsecond > 0:
        return dateval + timedelta(seconds=1, microseconds=-dateval.microsecond)
    return dateval


def datetime_repr(dateval):
    if dateval and isinstance(dateval, datetime):
        return dateval.strftime("%Y-%m-%d %H:%M:%S %Z")
    return "None" if dateval is None else dateval


def timezone_repr(timezone: tzinfo) -> str:
    if isinstance(timezone, ZoneInfo):
        return timezone.key

    return repr(timezone)


def get_callable_name(func):
    """
    Returns the best available display name for the given function/callable.

    :rtype: str

    """
    if ismethod(func):
        self = func.__self__
        cls = self if isclass(self) else type(self)
        return f"{cls.__qualname__}.{func.__name__}"
    elif isclass(func) or isfunction(func) or isbuiltin(func):
        return func.__qualname__
    elif hasattr(func, "__call__") and callable(func.__call__):
        # instance of a class with a __call__ method
        return type(func).__qualname__

    raise TypeError(
        f"Unable to determine a name for {func!r} -- maybe it is not a callable?"
    )


def obj_to_ref(obj):
    """
    Returns the path to the given callable.

    :rtype: str
    :raises TypeError: if the given object is not callable
    :raises ValueError: if the given object is a :class:`~functools.partial`, lambda or a nested
        function

    """
    if isinstance(obj, partial):
        raise ValueError("Cannot create a reference to a partial()")

    name = get_callable_name(obj)
    if "<lambda>" in name:
        raise ValueError("Cannot create a reference to a lambda")
    if "<locals>" in name:
        raise ValueError("Cannot create a reference to a nested function")

    if ismethod(obj):
        self = obj.__self__
        module = self.__module__
        module_obj = sys.modules.get(module)
        if module_obj:
            for var_name, var_val in vars(module_obj).items():
                if var_val is self:
                    func_name = obj.__name__
                    return f"{module}:{var_name}.{func_name}"
        return f"{module}:{name}"
    else:
        module = obj.__module__

    return f"{module}:{name}"


def ref_to_obj(ref: str, is_reload: bool = False):
    """Returns the object pointed to by ``ref``.

    Parameters
    ----------

    ref : str
        The string reference pointing to the object to be resolved.

        The format of the reference is ``module_name:object_name``.

        For example, ``"my_module:MyClass"`` or ``"my_module:my_function"``.

    is_reload : bool, optional
        If ``True``, the module will be reloaded if it has already been imported.

        Defaults to ``False``.

    Returns
    -------
    object
    The object pointed to by ``ref``.

    Raises
    ------
    TypeError
        If ``ref`` is not a string.
    ValueError
        If ``ref`` is not a valid reference (i.e., it does not contain a colon (:)).
    LookupError
        If the module specified in ``ref`` cannot be imported.

        If the object specified in ``ref`` cannot be found in the imported module.
    """
    if not isinstance(ref, str):
        raise TypeError('References must be strings')
    if ':' not in ref:
        raise ValueError('Invalid reference')

    modulename, rest = ref.split(':', 1)

    # Resolve filesystem paths (e.g. ./tasks/hello or ../other/module)
    if modulename.startswith(('./', '../')):
        file_path = pathlib.Path(modulename).resolve()

        # Strip .py extension if present so stem gives us the module name
        if file_path.suffix == '.py':
            modulename = file_path.stem
            parent_dir = str(file_path.parent.resolve())
        else:
            modulename = file_path.name
            parent_dir = str(file_path.parent.resolve())

        # Ensure the parent directory is on sys.path for imports
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

    try:
        if (modulename in sys.modules) and is_reload:
            obj = importlib.reload(sys.modules[modulename])
        else:
            obj = __import__(modulename, fromlist=[rest])
    except ImportError:
        raise LookupError('Error resolving reference %s: could not import module' % ref)

    try:
        for name in rest.split('.'):
            obj = getattr(obj, name)
        return obj
    except Exception:
        raise LookupError('Error resolving reference %s: error looking up object' % ref)


def maybe_ref(ref):
    """
    Returns the object that the given reference points to, if it is indeed a reference.
    If it is not a reference, the object is returned as-is.

    """
    if not isinstance(ref, str):
        return ref
    return ref_to_obj(ref)


def check_callable_args(func, args, kwargs):
    """
    Ensures that the given callable can be called with the given arguments.

    :type args: tuple
    :type kwargs: dict

    """
    pos_kwargs_conflicts = []  # parameters that have a match in both args and kwargs
    positional_only_kwargs = []  # positional-only parameters that have a match in kwargs
    unsatisfied_args = []  # parameters in signature that don't have a match in args or kwargs
    unsatisfied_kwargs = []  # keyword-only arguments that don't have a match in kwargs
    unmatched_args = list(
        args
    )  # args that didn't match any of the parameters in the signature
    # kwargs that didn't match any of the parameters in the signature
    unmatched_kwargs = list(kwargs)
    # indicates if the signature defines *args and **kwargs respectively
    has_varargs = has_var_kwargs = False

    try:
        sig = signature(func, follow_wrapped=False)
    except ValueError:
        # signature() doesn't work against every kind of callable
        return

    for param in sig.parameters.values():
        if param.kind == param.POSITIONAL_OR_KEYWORD:
            if param.name in unmatched_kwargs and unmatched_args:
                pos_kwargs_conflicts.append(param.name)
            elif unmatched_args:
                del unmatched_args[0]
            elif param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
            elif param.default is param.empty:
                unsatisfied_args.append(param.name)
        elif param.kind == param.POSITIONAL_ONLY:
            if unmatched_args:
                del unmatched_args[0]
            elif param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
                positional_only_kwargs.append(param.name)
            elif param.default is param.empty:
                unsatisfied_args.append(param.name)
        elif param.kind == param.KEYWORD_ONLY:
            if param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
            elif param.default is param.empty:
                unsatisfied_kwargs.append(param.name)
        elif param.kind == param.VAR_POSITIONAL:
            has_varargs = True
        elif param.kind == param.VAR_KEYWORD:
            has_var_kwargs = True

    # Make sure there are no conflicts between args and kwargs
    if pos_kwargs_conflicts:
        raise ValueError(
            "The following arguments are supplied in both args and kwargs: {}".format(
                ", ".join(pos_kwargs_conflicts)
            )
        )

    # Check if keyword arguments are being fed to positional-only parameters
    if positional_only_kwargs:
        raise ValueError(
            "The following arguments cannot be given as keyword arguments: {}".format(
                ", ".join(positional_only_kwargs)
            )
        )

    # Check that the number of positional arguments minus the number of matched kwargs
    # matches the argspec
    if unsatisfied_args:
        raise ValueError(
            "The following arguments have not been supplied: {}".format(
                ", ".join(unsatisfied_args)
            )
        )

    # Check that all keyword-only arguments have been supplied
    if unsatisfied_kwargs:
        raise ValueError(
            "The following keyword-only arguments have not been supplied in kwargs: "
            "{}".format(", ".join(unsatisfied_kwargs))
        )

    # Check that the callable can accept the given number of positional arguments
    if not has_varargs and unmatched_args:
        raise ValueError(
            f"The list of positional arguments is longer than the target callable can "
            f"handle (allowed: {len(args) - len(unmatched_args)}, given in args: "
            f"{len(args)})"
        )

    # Check that the callable can accept the given keyword arguments
    if not has_var_kwargs and unmatched_kwargs:
        raise ValueError(
            "The target callable does not accept the following keyword arguments: "
            "{}".format(", ".join(unmatched_kwargs))
        )


def iscoroutinefunction_partial(f):
    while isinstance(f, partial):
        f = f.func

    # The asyncio version of iscoroutinefunction includes testing for @coroutine
    # decorations vs. the inspect version which does not.
    return iscoroutinefunction(f)




class CustomTypeID(TypeID):
    """
    A custom TypeID class that extends the base TypeID class.

    Parameters
    ----------
    TypeID : TypeID
        The base TypeID class that this class extends.
    """
    def __init__(self, prefix: str = None, suffix: str = None):
        """
        Initializes a new instance of the CustomTypeID class.

        Parameters
        ----------
        prefix : str, optional
            The prefix to be used in the TypeID string representation.
            Defaults to None.
        suffix : str, optional
            The suffix to be used in the TypeID string representation.
            Defaults to None.
        """
        super().__init__(prefix=prefix, suffix=suffix)

    @classmethod
    def full_str(cls, prefix: str = None, suffix: str = None) -> str:
        """
        Returns the full string representation of the TypeID.

        Parameters
        ----------
        prefix : str, optional
            The prefix to be used in the TypeID string representation.
            Defaults to None.
        suffix : str, optional
            The suffix to be used in the TypeID string representation.
            Defaults to None.

        Returns
        -------
        str
            The full string representation of the TypeID.
        """
        return cls(prefix=prefix, suffix=suffix).__str__()
    
    @classmethod
    def partial_prefix(cls, prefix: str = None) -> partial:
        """
        Returns a partial function that generates a string representation of the TypeID with the given prefix.

        Parameters
        ----------
        prefix : str, optional
            The prefix to be used in the TypeID string representation.
            Defaults to None.

        Returns
        -------
        partial
            A partial function that takes no arguments and returns a string representation of the TypeID with the given prefix.
        """
        return partial(cls.full_str, prefix=prefix)

    def __repr__(self):
        return f"<class CustomTypeID({self.__str__()})>"


def for_test_callable(random_value: int = None, threshold: int = 60, wait: int = 1, **kwargs):
    """A callable function node used for testing."""
    import random
    from time import sleep
    if not random_value:
        random_value = random.randint(1, 100)
    if random_value < threshold:
        raise ValueError(f"random raise error: {random_value} < threshold({threshold})")
    sleep(wait)
    return {
        **kwargs,
        "random_value": random_value
    }


def for_test_add_all(_pre_results, **kwargs):
    """A callable function node used for testing."""
    print(f"for_test_add_all: {kwargs=}, 前置结果: {_pre_results}")
    return {node_id: v.get('random_value') for node_id, v in _pre_results.items()}


def for_test_edge_condition(exec_log) -> bool:
    """Check the boundary condition for a test node."""
    res = exec_log.result
    print(f"for_test_edge_condition: {exec_log=}, {res=}")
    if res['random_value'] < 55:
        return False
    return True


def for_test_callable_done(retval=None, exc_info=None, **kwargs):
    """Callback function used for testing node execution completion."""
    if exc_info:
        import traceback
        # exc_print = "".join(traceback.format_exception(type(exc_info[0]), exc_info[1], exc_info[2].__traceback__))
        exc_print = "".join(traceback.format_exception(exc_info[0], exc_info[1], exc_info[2]))
        print("报错回调", retval, exc_print, kwargs)
        return
    return f"任务成功回调: {retval=}, {exc_info=}, {kwargs=}"



if __name__ == "__main__":
    from typeid import TypeID

    typeid = CustomTypeID(prefix="abc")
    # print(typeid.prefix, typeid.suffix, typeid.uuid)
    # print(typeid, type(typeid), typeid.__repr__())

    ss = "2025-07-13T17:03:45+08:00"
    r2 = convert_to_datetime(ss, None)
    print(type(r2), r2)
    print(datetime_to_string(r2))
