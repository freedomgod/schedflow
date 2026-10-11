"""Private provider settings, write-only credentials and independent tool probes."""

import asyncio
import json
import logging
import re
from contextlib import aclosing
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from schedflow.configs import config as metadata

from .config import AgentConfig

PROTOCOLS = {
    "custom": {"chat_completions", "responses", "anthropic_messages"},
    "openai": {"responses", "chat_completions"},
    "deepseek": {"chat_completions"},
    "qwen": {"chat_completions"},
    "kimi": {"chat_completions"},
    "glm": {"chat_completions"},
    "claude": {"anthropic_messages"},
    "gemini": {"chat_completions"},
}


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider: str = Field(max_length=32)
    protocol: str = Field(max_length=32)
    base_url: str = Field(max_length=2048)
    model: str = Field(max_length=200)
    enabled: bool = False
    region: str = Field(default="", max_length=100)
    workspace_id: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, repr=False)
    clear_api_key: bool = False
    max_steps: int = Field(default=8, ge=1, le=32)
    timeout: float = Field(default=60, gt=0, le=600)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    allow_code_generation: bool = False
    retention_days: int = Field(default=30, ge=1, le=3650)


def validate_config(config, *, check_model_capabilities=True):
    if (
        config.provider not in PROTOCOLS
        or config.protocol not in PROTOCOLS[config.provider]
    ):
        raise ValueError("Unsupported provider or protocol")
    if not config.model.strip() or any(ord(c) < 32 for c in config.model):
        raise ValueError("Configure a valid model ID")
    try:
        parsed = urlsplit(config.base_url)
        _ = parsed.port
        valid = (
            parsed.scheme in {"https", "http"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and not re.search(r"[\s{}<>\\]", config.base_url)
            and not any(ord(c) < 32 for c in config.base_url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "Use an HTTP(S) API root without credentials, query or placeholders"
        )
    if parsed.scheme != "https" and config.provider != "custom":
        raise ValueError("Official provider profiles require HTTPS")
    if check_model_capabilities and (
        config.provider == "kimi"
        or (config.provider == "custom" and parsed.hostname == "api.moonshot.cn")
    ):
        model = config.model.strip().lower()
        if any(
            model == family or model.startswith(family + "-")
            for family in ("kimi-k3", "kimi-k2.7-code")
        ):
            raise ValueError(
                "This Kimi model requires preserved reasoning across user turns, "
                "which this Agent does not persist. Choose kimi-k2.6."
            )
    if config.provider != "custom" and not config.api_key:
        raise ValueError("Configure this provider's API key")
    if len(config.api_key) > 8192 or any(ord(c) < 32 for c in config.api_key):
        raise ValueError("Invalid API key")


def config_candidate(current, changes):
    try:
        body = ConfigUpdate.model_validate(changes)
    except ValidationError:
        raise ValueError("Invalid Agent configuration parameters") from None
    values = current.model_dump()
    values.update(
        body.model_dump(exclude_unset=True, exclude={"api_key", "clear_api_key"})
    )
    values["base_url"] = values["base_url"].strip().rstrip("/")
    values["model"] = values["model"].strip()
    old_identity = (
        current.provider,
        current.protocol,
        current.base_url.rstrip("/"),
        current.workspace_id,
    )
    new_identity = tuple(
        values[k] for k in ("provider", "protocol", "base_url", "workspace_id")
    )
    key = body.api_key.strip() if body.api_key else ""
    if body.clear_api_key and key:
        raise ValueError("Choose either a new API key or clear the saved key")
    if body.clear_api_key:
        values["api_key"] = ""
    elif key:
        values["api_key"] = key
    elif old_identity != new_identity and current.api_key:
        raise ValueError(
            "Provider or destination changed: supply a new API key or explicitly clear it"
        )
    candidate = AgentConfig(**values)
    # Always validate destinations before saving, including disabled configurations.
    # Unconfigured/cleared profiles may remain disabled.
    validation = candidate.model_copy(
        update={
            "model": candidate.model or "unconfigured",
            "api_key": candidate.api_key or "unconfigured",
        }
    )
    validate_config(validation, check_model_capabilities=candidate.enabled)
    if candidate.enabled:
        validate_config(candidate)
    return candidate


def public_config(config, source):
    data = config.model_dump(exclude={"api_key"})
    data.update(config.public_status(), has_api_key=bool(config.api_key), source=source)
    return data


class AgentSettings:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory

    def load(self, fallback):
        conn = (self.connection_factory or metadata._get_conn)()
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='agent_config'"
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return fallback, "environment"
        try:
            # Supply every field so process environment cannot override saved values.
            saved = AgentConfig(**json.loads(row[0]))
            config_candidate(
                saved,
                {
                    **saved.model_dump(exclude={"api_key"}),
                    "api_key": saved.api_key,
                    # Restore structurally valid legacy configurations for the
                    # settings UI to repair/disable. Runtime capability checks
                    # still reject them; the stored enabled flag stays intact.
                    "enabled": False,
                },
            )
            if saved.enabled:
                validate_config(saved, check_model_capabilities=False)
        except (ValueError, TypeError):
            raise ValueError("Stored Agent configuration is invalid") from None
        return saved, "database"

    def save(self, config):
        conn = (self.connection_factory or metadata._get_conn)()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO system_settings(key,value,updated_at) VALUES('agent_config',?,datetime('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (json.dumps(config.model_dump()),),
                )
        finally:
            conn.close()


async def probe_config(config, provider_factory=None):
    """Verify a harmless tool loop; never read the scheduler or save a configuration."""
    from .provider import create_provider

    validate_config(config)
    probe = config.model_copy(
        update={
            "timeout": min(config.timeout, 30),
            "max_tokens": min(config.max_tokens, 4096),
        }
    )
    provider = (provider_factory or create_provider)(probe)
    messages = [
        {
            "role": "system",
            "content": "Call schedflow_connection_probe once with nonce connection-check. After its result, reply OK. This is a connectivity test.",
        },
        {"role": "user", "content": "Test tool calling now."},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "schedflow_connection_probe",
                "description": "Harmless connection test",
                "parameters": {
                    "type": "object",
                    "properties": {"nonce": {"type": "string"}},
                    "required": ["nonce"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    try:
        async with asyncio.timeout(probe.timeout):
            text, calls, assistant = [], [], None
            async with aclosing(provider.stream(messages, tools)) as stream:
                async for event in stream:
                    if event["type"] == "text":
                        text.append(event["text"])
                    elif event["type"] == "tool_call":
                        calls.append(event)
                    elif event["type"] == "assistant_message":
                        assistant = event["message"]
            if (
                len(calls) != 1
                or calls[0]["name"] != "schedflow_connection_probe"
                or json.loads(calls[0]["arguments"]) != {"nonce": "connection-check"}
            ):
                return {
                    "success": False,
                    "message": "连接可达，但模型没有完成测试工具调用；请确认模型支持工具。",
                }
            messages.append(
                assistant
                or {
                    "role": "assistant",
                    "content": "".join(text) or None,
                    "tool_calls": [
                        {
                            "id": calls[0]["id"],
                            "type": "function",
                            "function": {
                                "name": calls[0]["name"],
                                "arguments": calls[0]["arguments"],
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": calls[0]["id"],
                    "content": '{"ok":true}',
                }
            )
            followup = []
            async with aclosing(provider.stream(messages, tools)) as stream:
                async for event in stream:
                    if event["type"] == "text":
                        followup.append(event["text"])
                    elif event["type"] == "tool_call":
                        return {
                            "success": False,
                            "message": "模型未结束测试工具循环，请检查模型兼容性。",
                        }
            if not "".join(followup).strip():
                return {
                    "success": False,
                    "message": "模型没有返回测试工具执行后的回复。",
                }
        return {"success": True, "message": "连接、工具调用及结果回传测试通过。"}
    except Exception:  # noqa: BLE001 -- provider exceptions may contain credential-bearing request details
        return {
            "success": False,
            "message": "测试失败，请检查地址、模型权限、API Key 或网络连接。",
        }
    finally:
        if hasattr(provider, "close"):
            try:
                await provider.close()
            except Exception:  # noqa: BLE001 -- cleanup errors must not leak provider request data
                logging.getLogger(__name__).warning(
                    "Agent probe connection cleanup failed"
                )
