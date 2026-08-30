"""Runner for python_callable tasks — direct function invocation.

References are resolved lazily here (at execution time), so jobs can be
created and persisted even when the target module is not importable in the
current process.
"""

import concurrent.futures
import inspect

from schedflow.core.resolve import resolve_ref
from schedflow.core.result import TaskResult

from .base import BaseRunner, RunContext


def _filter_kwargs(func, kwargs: dict) -> dict:
    """Keep only keyword arguments the callable accepts."""
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return kwargs
    has_var_keyword = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in parameters.values()
    )
    return {
        key: value
        for key, value in kwargs.items()
        if key in parameters or has_var_keyword
    }


class PythonCallableRunner(BaseRunner):
    def run(self, spec, *, context: RunContext | None = None, **kwargs) -> TaskResult:
        context = context or RunContext()
        try:
            func = spec.func
            if func is None:
                func = resolve_ref(spec.ref, project_root=context.project_root)
            args = list(getattr(spec, "args", None) or [])
            run_kwargs = dict(getattr(spec, "kwargs", None) or {})
            run_kwargs.update(kwargs)
            run_kwargs = _filter_kwargs(func, run_kwargs)
            timeout = getattr(spec, "timeout", None)
            result = self._invoke(func, args, run_kwargs, timeout)
            return TaskResult(succeeded=True, result=result)
        except TimeoutError:
            return TaskResult(
                succeeded=False,
                error=f"Task timed out after {timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(succeeded=False, error=str(exc))

    def _invoke(self, func, args, kwargs, timeout):
        def call():
            return func(*args, **kwargs)

        if timeout is None:
            return call()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(call).result(timeout=timeout)
