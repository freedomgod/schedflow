"""Tests for the TaskSpec and TaskResult core objects."""

import pytest

from schedflow.core.spec import TaskSpec
from schedflow.core.result import TaskResult


def dummy_func(a: int = 1, b: int = 2) -> int:
    """Module-level function used for ref serialization tests."""
    return a + b


class TestTaskSpec:
    def test_string_func_sets_ref(self):
        spec = TaskSpec(func="pkg.mod:fn")

        assert spec.type == "python_callable"
        assert spec.ref == "pkg.mod:fn"
        assert spec.func is None

    def test_callable_keeps_func_and_serializes_to_ref(self):
        spec = TaskSpec(func=dummy_func)

        assert spec.func is dummy_func
        data = spec.to_dict()
        assert data["type"] == "python_callable"
        assert data["ref"].endswith(":dummy_func")
        assert "func" not in data

    def test_from_dict_keeps_ref_unresolved(self):
        spec = TaskSpec.from_dict(
            {"type": "python_callable", "ref": "nonexistent_module:fn"}
        )

        assert spec.ref == "nonexistent_module:fn"
        assert spec.func is None

    def test_bash_requires_command(self):
        with pytest.raises(ValueError, match="command"):
            TaskSpec(type="bash")

    def test_python_requires_script_path(self):
        with pytest.raises(ValueError, match="script_path"):
            TaskSpec(type="python")

    def test_python_script_requires_script(self):
        with pytest.raises(ValueError, match="script"):
            TaskSpec(type="python_script")

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError, match="type"):
            TaskSpec(type="powershell")

    def test_lambda_raises_on_serialize_with_clear_message(self):
        spec = TaskSpec(func=lambda: 1)

        with pytest.raises(ValueError, match="lambda"):
            spec.to_dict()

    def test_to_dict_roundtrip_all_types(self):
        cases = [
            TaskSpec(type="bash", command="echo hi", timeout=10),
            TaskSpec(type="python", script_path="./run.py", args=["a"]),
            TaskSpec(type="python_script", script="print(1)"),
            TaskSpec(
                type="python_callable",
                func=dummy_func,
                args=[1],
                kwargs={"b": 3},
                timeout=5,
            ),
        ]
        for spec in cases:
            restored = TaskSpec.from_dict(spec.to_dict())
            assert restored.type == spec.type
            assert restored.to_dict() == spec.to_dict()

    def test_defaults(self):
        spec = TaskSpec(func="pkg.mod:fn")
        assert spec.args == []
        assert spec.kwargs == {}
        assert spec.timeout is None


class TestTaskResult:
    def test_success_result(self):
        result = TaskResult(succeeded=True, result=42)
        assert result.succeeded is True
        assert result.result == 42

    def test_failure_result(self):
        result = TaskResult(succeeded=False, error="boom", exit_code=1)
        assert not result.succeeded
        assert result.error == "boom"

    def test_to_dict_roundtrip(self):
        result = TaskResult(
            succeeded=True,
            result={"key": "value"},
            stdout="out",
            stderr="err",
            exit_code=0,
            duration=1.5,
        )
        restored = TaskResult.from_dict(result.to_dict())
        assert restored.succeeded is True
        assert restored.result == {"key": "value"}
        assert restored.stdout == "out"
        assert restored.duration == 1.5
