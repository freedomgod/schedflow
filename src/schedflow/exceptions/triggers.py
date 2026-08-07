"""定义触发器相关错误类型
"""

from pydantic import ValidationError


class TriggerError(Exception):
    """所有触发器异常的基类"""
    def __init__(self, message: str = "Trigger error occurred", trigger_type: str = None):
        self.trigger_type = trigger_type
        super().__init__(f"[{trigger_type}] {message}" if trigger_type else message)


class TriggerValidationError(TriggerError):
    def __init__(self, message: str = "参数验证错误", trigger_type: str = None):
        super().__init__(message, trigger_type)
