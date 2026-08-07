"""Tests for trigger exception types."""

import pytest
from pydantic import ValidationError

from schedflow.exceptions.triggers import TriggerError, TriggerValidationError


class TestTriggerError:
    def test_default_message(self):
        exc = TriggerError()
        assert "Trigger error occurred" in str(exc)
        assert exc.trigger_type is None

    def test_custom_message(self):
        exc = TriggerError("Custom error")
        assert str(exc) == "Custom error"
        assert exc.trigger_type is None

    def test_custom_message_with_trigger_type(self):
        exc = TriggerError("Bad config", trigger_type="CronTrigger")
        assert str(exc) == "[CronTrigger] Bad config"
        assert exc.trigger_type == "CronTrigger"

    def test_is_exception_subclass(self):
        exc = TriggerError("test")
        assert isinstance(exc, Exception)


class TestTriggerValidationError:
    def test_default_message(self):
        exc = TriggerValidationError()
        assert "参数验证错误" in str(exc)
        assert exc.trigger_type is None

    def test_custom_message(self):
        exc = TriggerValidationError("Invalid field", trigger_type="DateTrigger")
        assert str(exc) == "[DateTrigger] Invalid field"
        assert exc.trigger_type == "DateTrigger"

    def test_is_trigger_error_subclass(self):
        exc = TriggerValidationError("test")
        assert isinstance(exc, TriggerError)
        assert isinstance(exc, Exception)
