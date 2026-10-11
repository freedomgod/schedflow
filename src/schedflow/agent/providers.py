"""Verified provider defaults (2026-10-11); account access is not guaranteed."""

from copy import deepcopy

_QWEN_REGIONS = [
    {
        "id": region,
        "label": label,
        "base_url": "https://{WorkspaceId}."
        + region
        + ".maas.aliyuncs.com/compatible-mode/v1",
    }
    for region, label in [
        ("cn-beijing", "北京"),
        ("ap-southeast-1", "新加坡"),
        ("us-east-1", "美国弗吉尼亚"),
    ]
]
_PROVIDERS = [
    {
        "id": "openai",
        "label": "OpenAI",
        "protocol": "responses",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-6.1-sol", "gpt-6-astra"],
        "requires_api_key": True,
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "protocol": "chat_completions",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "requires_api_key": True,
    },
    {
        "id": "qwen",
        "label": "阿里云百炼 Qwen",
        "protocol": "chat_completions",
        "base_url": _QWEN_REGIONS[0]["base_url"],
        "models": ["qwen3.8-max", "qwen3.7-plus"],
        "requires_api_key": True,
        "regions": _QWEN_REGIONS,
    },
    {
        "id": "kimi",
        "label": "Moonshot Kimi",
        "protocol": "chat_completions",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2.6"],
        "requires_api_key": True,
    },
    {
        "id": "glm",
        "label": "智谱 GLM",
        "protocol": "chat_completions",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3"],
        "requires_api_key": True,
    },
    {
        "id": "claude",
        "label": "Anthropic Claude",
        "protocol": "anthropic_messages",
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-sonnet-5-5", "claude-haiku-5-5"],
        "requires_api_key": True,
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "protocol": "chat_completions",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-3.8-flash", "gemini-3.5-flash-lite"],
        "requires_api_key": True,
    },
    {
        "id": "custom",
        "label": "自定义",
        "protocol": "chat_completions",
        "base_url": "",
        "models": [],
        "requires_api_key": False,
    },
]


def provider_catalog():
    """Return plain JSON defaults without exposing mutable module state."""
    return deepcopy(_PROVIDERS)
