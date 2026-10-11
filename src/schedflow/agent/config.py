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
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key: str = Field(default="", repr=False)
    max_steps: int = Field(default=8, ge=1, le=32)
    timeout: float = Field(default=60, gt=0, le=600)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    allow_code_generation: bool = False
    retention_days: int = Field(default=30, ge=1, le=3650)

    def public_status(self):
        configured = bool(self.model and self.base_url)
        parsed = urlsplit(self.base_url)
        safe_url = urlunsplit(
            (parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", "")
        )
        return {
            "enabled": self.enabled,
            "configured": configured,
            "model": self.model,
            "base_url": safe_url,
            "reason": None
            if self.enabled and configured
            else (
                "Agent is disabled"
                if not self.enabled
                else "Configure a model and base URL"
            ),
        }
