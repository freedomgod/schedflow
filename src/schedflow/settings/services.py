import json
from zoneinfo import available_timezones

from tzlocal import get_localzone

from schedflow.settings.models import delete_setting, get_setting, set_setting
from schedflow.utils import astimezone

DEFAULT_RATE_LIMIT = {"enabled": False, "rpm": 120}

#: ``system_settings`` key holding the operator-selected default timezone.
TIMEZONE_KEY = "timezone"


def _timezone_name(tz) -> str:
    """Return the IANA name of a tzinfo (``ZoneInfo.key`` when available)."""
    return getattr(tz, "key", None) or str(tz)


def get_system_timezone() -> str:
    """Name of the zone the process itself runs in (container ``TZ``/``/etc/localtime``)."""
    return _timezone_name(get_localzone())


def get_configured_timezone() -> str | None:
    """The persisted default timezone name, or ``None`` when never configured."""
    return get_setting(TIMEZONE_KEY) or None


def resolve_timezone(name: str):
    """Validate ``name`` and return its tzinfo.

    Raises:
        ValueError: the name is not a known IANA zone (or the installation
            has no timezone database at all, e.g. a slim container image
            without ``tzdata``).
    """
    try:
        return astimezone(name)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(
            f"未知的时区 {name!r}：请使用 IANA 时区名（如 Asia/Shanghai）。"
            f"若容器镜像缺少时区数据库，请安装 tzdata（{exc}）。"
        ) from exc


def set_timezone(name: str | None) -> str | None:
    """Persist the system default timezone; ``None`` clears it.

    Clearing restores the previous behaviour of following the process-local
    zone, so operators always have a way back if a value misbehaves.
    """
    if name is None:
        delete_setting(TIMEZONE_KEY)
        return None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("时区名不能为空")
    name = name.strip()
    resolve_timezone(name)
    set_setting(TIMEZONE_KEY, name)
    return name


def get_default_timezone() -> str:
    """Effective default timezone for newly scheduled work.

    Precedence: the configured setting, otherwise the process-local zone
    (which is ``Etc/UTC`` inside a container that does not set ``TZ``).
    A configured value that no longer resolves -- e.g. the image lost its
    timezone database -- falls back to the local zone instead of breaking
    every new job.
    """
    configured = get_configured_timezone()
    if configured:
        try:
            resolve_timezone(configured)
            return configured
        except ValueError:
            pass
    return get_system_timezone()


def list_timezones() -> list[str]:
    """Sorted IANA names known to this installation (empty without tzdata)."""
    return sorted(available_timezones())


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
