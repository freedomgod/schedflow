"""Runner tests: lazy reference resolution, subprocess env/cwd/timeout."""

from pathlib import Path

import pytest

from schedflow.core.resolve import RefResolveError, resolve_ref
from schedflow.core.spec import TaskSpec
from schedflow.runners.base import RunContext
from schedflow.runners.registry import RunnerRegistry


def module_fn(a: int = 1, b: int = 2) -> int:
    return a + b


def slow_fn():
    import time

    time.sleep(1)
    return "late"


def default_context(tmp_path: Path | None = None, **kwargs) -> RunContext:
    return RunContext(project_root=tmp_path, **kwargs)


class TestResolveRef:
    def test_module_ref(self):
        obj = resolve_ref("tests.core.test_runners:module_fn")
        assert obj is module_fn

    def test_absolute_path_ref(self, tmp_path):
        script = tmp_path / "mytasks.py"
        script.write_text("def hello(name='world'):\n    return 'hello ' + name\n", encoding="utf-8")
        obj = resolve_ref(f"{script.as_posix()}:hello")
        assert obj("codex") == "hello codex"

    def test_relative_path_ref_with_project_root(self, tmp_path):
        (tmp_path / "mytasks.py").write_text(
            "def hello():\n    return 'ok'\n", encoding="utf-8"
        )
        obj = resolve_ref("./mytasks.py:hello", project_root=tmp_path)
        assert obj() == "ok"

    def test_invalid_ref_format(self):
        with pytest.raises(RefResolveError, match="reference"):
            resolve_ref("no-colon-here")

    def test_failure_message_mentions_attempts(self, tmp_path):
        with pytest.raises(RefResolveError) as exc_info:
            resolve_ref("missing_module_xyz:fn", project_root=tmp_path)
        assert "missing_module_xyz" in str(exc_info.value)


class TestPythonCallableRunner:
    def test_runs_callable_directly(self):
        runner = RunnerRegistry.get("python_callable")
        spec = TaskSpec(func=module_fn, kwargs={"a": 3})
        result = runner.run(spec, context=default_context())
        assert result.succeeded
        assert result.result == 5

    def test_runs_ref_lazily(self):
        runner = RunnerRegistry.get("python_callable")
        spec = TaskSpec(func="tests.core.test_runners:module_fn", kwargs={"b": 10})
        result = runner.run(spec, context=default_context())
        assert result.succeeded
        assert result.result == 11

    def test_resolves_absolute_path_ref(self, tmp_path):
        script = tmp_path / "mytasks.py"
        script.write_text("def hello(name='world'):\n    return 'hello ' + name\n", encoding="utf-8")
        spec = TaskSpec(func=f"{script.as_posix()}:hello")
        result = RunnerRegistry.get("python_callable").run(
            spec, context=default_context()
        )
        assert result.succeeded
        assert result.result == "hello world"

    def test_resolves_relative_path_ref_with_project_root(self, tmp_path):
        (tmp_path / "mytasks.py").write_text(
            "def hello():\n    return 'ok'\n", encoding="utf-8"
        )
        spec = TaskSpec(func="./mytasks.py:hello")
        result = RunnerRegistry.get("python_callable").run(
            spec, context=default_context(tmp_path)
        )
        assert result.succeeded
        assert result.result == "ok"

    def test_unresolvable_ref_returns_failed_result(self, tmp_path):
        spec = TaskSpec(func="missing_module_xyz:fn")
        result = RunnerRegistry.get("python_callable").run(
            spec, context=default_context(tmp_path)
        )
        assert not result.succeeded
        assert "missing_module_xyz" in result.error

    def test_timeout_marks_failed(self):
        spec = TaskSpec(func="tests.core.test_runners:slow_fn", timeout=0.05)
        result = RunnerRegistry.get("python_callable").run(
            spec, context=default_context()
        )
        assert not result.succeeded
        assert "timed out" in result.error.lower()


class TestBashRunner:
    def test_runs_command(self):
        spec = TaskSpec(type="bash", command="echo hello")
        result = RunnerRegistry.get("bash").run(spec, context=default_context())
        assert result.succeeded
        assert "hello" in (result.stdout or "")

    def test_failed_command_reports_exit_code(self):
        spec = TaskSpec(type="bash", command="exit 3")
        result = RunnerRegistry.get("bash").run(spec, context=default_context())
        assert not result.succeeded
        assert result.exit_code == 3


class TestPythonFileRunner:
    def test_runs_script_file_with_args(self, tmp_path):
        script = tmp_path / "run.py"
        script.write_text(
            "import sys\nprint('args=' + ','.join(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        spec = TaskSpec(type="python", script_path=str(script), args=["a", "b"])
        result = RunnerRegistry.get("python").run(spec, context=default_context())
        assert result.succeeded
        assert "args=a,b" in (result.stdout or "")


class TestPythonScriptRunner:
    def test_runs_inline_script(self):
        spec = TaskSpec(type="python_script", script="print(1 + 1)")
        result = RunnerRegistry.get("python_script").run(
            spec, context=default_context()
        )
        assert result.succeeded
        assert "2" in (result.stdout or "")

    def test_env_and_cwd(self, tmp_path):
        spec = TaskSpec(
            type="python_script",
            script="import os\nprint(os.environ['FOO'])\nprint(os.getcwd())",
        )
        result = RunnerRegistry.get("python_script").run(
            spec, context=default_context(env={"FOO": "bar"}, cwd=tmp_path)
        )
        assert result.succeeded
        assert "bar" in (result.stdout or "")
        assert str(tmp_path) in (result.stdout or "")

    def test_timeout(self):
        spec = TaskSpec(
            type="python_script",
            script="import time; time.sleep(30)",
            timeout=0.3,
        )
        result = RunnerRegistry.get("python_script").run(
            spec, context=default_context()
        )
        assert not result.succeeded
        assert "timed out" in result.error.lower()
