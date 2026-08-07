from schedflow.settings.models import get_setting, set_setting


def get_theme() -> str:
    theme = get_setting("theme")
    return theme if theme in ("light", "dark") else "light"


def set_theme(theme: str) -> None:
    if theme not in ("light", "dark"):
        raise ValueError("theme must be 'light' or 'dark'")
    set_setting("theme", theme)
