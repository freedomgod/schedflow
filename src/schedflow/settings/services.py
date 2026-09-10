import json

from schedflow.settings.models import get_setting, set_setting

DEFAULT_RATE_LIMIT = {"enabled": False, "rpm": 120}


def get_theme() -> str:
    theme = get_setting("theme")
    return theme if theme in ("light", "dark") else "light"


def set_theme(theme: str) -> None:
    if theme not in ("light", "dark"):
        raise ValueError("theme must be 'light' or 'dark'")
    set_setting("theme", theme)


def get_webhooks_config() -> list[dict]:
    raw = get_setting("webhooks")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def set_webhooks_config(configs: list[dict]) -> None:
    set_setting("webhooks", json.dumps(configs, ensure_ascii=False))


def get_rate_limit_config() -> dict:
    raw = get_setting("rate_limit")
    if not raw:
        return dict(DEFAULT_RATE_LIMIT)
    try:
        data = json.loads(raw)
    except ValueError:
        return dict(DEFAULT_RATE_LIMIT)
    return {
        "enabled": bool(data.get("enabled", False)),
        "rpm": max(1, int(data.get("rpm", 120))),
    }


def set_rate_limit_config(config: dict) -> None:
    normalized = {
        "enabled": bool(config.get("enabled", False)),
        "rpm": max(1, int(config.get("rpm", 120))),
    }
    set_setting("rate_limit", json.dumps(normalized))
