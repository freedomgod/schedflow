"""Application settings management.

Settings are loaded from environment variables and .env files using
pydantic-settings. The Settings class defines all configurable parameters
including server host/port, logging, database URLs, and more.

The metadata database path (``SCHEDFLOW_META_DB``) is resolved against the
project root rather than the current working directory, so the same database
is used no matter where the process is launched from. It defaults to
``data/scheduler_meta.db`` so runtime files stay out of the repository root.

The .env file itself defaults to ``<project root>/.env``. When the package is
installed non-editable (e.g. inside a Docker image) that location points into
site-packages, so deployments may point the settings loader at a mounted file
through the ``SCHEDFLOW_ENV_FILE`` environment variable (for example
``SCHEDFLOW_ENV_FILE=/app/.env`` in docker compose).
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Locate the project root from the package file location.

    Prefers the directory containing ``pyproject.toml`` (editable/dev layout).
    Falls back to the package parent directory for installed (wheel) layouts.
    This is independent of the process working directory.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[1]


PROJECT_ROOT = _find_project_root()

#: .env 文件路径。默认取项目根目录；容器等非可编辑安装场景可通过
#: SCHEDFLOW_ENV_FILE 环境变量指向挂载进来的配置文件（如 /app/.env）。
_ENV_FILE = os.environ.get("SCHEDFLOW_ENV_FILE") or str(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    APP_ENV: str = "production"

    # ── Server ───────────────────────────────────────────
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    RELOAD: bool = False
    WORKERS: int = 1

    # ── Logging ──────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Metadata DB ──────────────────────────────────────
    SCHEDFLOW_META_DB: str = "data/scheduler_meta.db"

    @property
    def meta_db_path(self) -> Path:
        """Absolute path of the metadata database.

        Relative paths are resolved against the project root, so launching
        from a different working directory always uses the same database.
        Absolute paths (or ``~`` prefixed paths) are used as-is.
        """
        path = Path(self.SCHEDFLOW_META_DB).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    # ── Redis ────────────────────────────────────────────
    SCHEDFLOW_REDIS_HOST: str = "localhost"
    SCHEDFLOW_REDIS_PORT: int = 6379
    SCHEDFLOW_REDIS_USERNAME: str | None = None
    SCHEDFLOW_REDIS_PASSWORD: str | None = None
    SCHEDFLOW_REDIS_DB: int = 0

    # ── MongoDB ──────────────────────────────────────────
    SCHEDFLOW_MONGODB_HOST: str = "localhost"
    SCHEDFLOW_MONGODB_PORT: int = 27017
    SCHEDFLOW_MONGODB_USERNAME: str | None = None
    SCHEDFLOW_MONGODB_PASSWORD: str | None = None
    SCHEDFLOW_MONGODB_AUTH_SOURCE: str = "admin"


settings = Settings()
