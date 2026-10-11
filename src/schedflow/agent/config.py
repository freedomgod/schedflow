"""Optional personal assistant configuration; credentials stay on the server."""

from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from schedflow.configs.settings import _ENV_FILE


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHEDFLOW_AGENT_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )
    enabled: bool = False
    # Existing environment configurations keep the original compatible protocol.
    provider: str = "custom"
    protocol: str = "chat_completions"
    region: str = ""
    workspace_id: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: str = Field(default="", repr=False)
    max_steps: int = Field(default=8, ge=1, le=32)
    timeout: float = Field(default=60, gt=0, le=600)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    allow_code_generation: bool = False
    retention_days: int = Field(default=30, ge=1, le=3650)

    def public_status(self):
        from .settings import validate_config

        try:
            validate_config(self)
            configured = True
            reason = None
        except ValueError as exc:
            configured = False
            reason = str(exc)
        try:
            parsed = urlsplit(self.base_url)
            safe_url = urlunsplit(
                (parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", "")
            )
        except ValueError:
            safe_url = ""
        return {
            "enabled": self.enabled,
            "configured": configured,
            "model": self.model,
            "provider": self.provider,
            "protocol": self.protocol,
            "runtime": "langgraph",
            "base_url": safe_url,
            "reason": None
            if self.enabled and configured
            else (
                "Agent is disabled"
                if not self.enabled
                else reason
            ),
        }
