"""Command-line entry points for the backend API and the web dashboard.

Both commands default to **production mode**; development behaviour is only
enabled when ``--dev`` is passed explicitly::

    schedflow-backend            # production: no reload watcher, INFO logs
    schedflow-backend --dev      # development: hot reload + DEBUG logs
    schedflow-frontend           # production: build (if needed) + vite preview
    schedflow-frontend --dev     # development: Vite dev server with HMR
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from schedflow.configs.settings import settings
from schedflow.core import Scheduler

try:
    import uvicorn

    from schedflow.api import create_app

    app = create_app(
        Scheduler(),
        title="调度器API",
        description="SchedFlow REST API",
        version="1.0.0",
    )
except ImportError:  # pragma: no cover - optional 'web' extra
    # Importing this module (used by schedflow-frontend and programmatic
    # entry points) must not require the optional web extra. The backend
    # command checks uvicorn/app and explains how to install them.
    uvicorn = None
    app = None

#: Files the dev reloader should ignore so jobs.db writes and Git fsmonitor
#: cookies do not spam "X changes detected" logs (or trigger restarts).
RELOAD_EXCLUDES = [
    ".git/**",
    "**/.git/**",
    "*.db",
    "*.db-journal",
    "*.sqlite",
    "*.sqlite3",
    "node_modules/**",
    "dist/**",
]


def _backend_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedflow-backend",
        description="Start the SchedFlow backend API server "
        "(production by default; pass --dev for hot reload).",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="开发模式：启用热重载与 DEBUG 日志（默认是生产模式）",
    )
    parser.add_argument("--host", default=None, help="监听地址（默认取自 .env）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认取自 .env）")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="worker 进程数（仅生产模式生效，默认取自 .env）",
    )
    return parser


def backend() -> None:
    """Start the backend API server (production by default)."""
    args = _backend_parser().parse_args()

    if uvicorn is None or app is None:  # pragma: no cover
        raise SystemExit(
            "schedflow-backend requires the 'web' extra. "
            "Install it with: pip install schedflow[web]"
        )

    if args.dev:
        settings.RELOAD = True
        settings.LOG_LEVEL = "DEBUG"
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        settings.RELOAD = False
        settings.LOG_LEVEL = settings.LOG_LEVEL or "INFO"
        logging.getLogger().setLevel(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        )

    # Ensure CWD is on sys.path so user modules (e.g. tasks/hello.py) are
    # importable from the same process.
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # With reload, uvicorn needs an import string so the worker picks up the
    # app freshly on every restart.
    target = "schedflow.cli:app" if settings.RELOAD else app
    uvicorn.run(
        target,
        host=args.host or settings.HOST,
        port=args.port or settings.PORT,
        reload=settings.RELOAD,
        reload_excludes=RELOAD_EXCLUDES if settings.RELOAD else None,
        workers=1 if settings.RELOAD else (args.workers or settings.WORKERS),
    )


def _frontend_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedflow-frontend",
        description="Start the SchedFlow web dashboard "
        "(production preview by default; pass --dev for the Vite dev server).",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="开发模式：运行 Vite 开发服务器（热更新；默认是生产预览）",
    )
    parser.add_argument("--host", default=None, help="预览服务器监听地址")
    parser.add_argument("--port", type=int, default=None, help="预览服务器监听端口")
    return parser


def _frontend_needs_build(frontend_dir: Path) -> bool:
    """True when dist is missing or any frontend source is newer than it."""
    dist = frontend_dir / "dist"
    index = dist / "index.html"
    if not index.exists():
        return True
    built_at = index.stat().st_mtime
    roots = ["index.html", "vite.config.ts", "package.json", "src"]
    for root in roots:
        path = frontend_dir / root
        if not path.exists():
            continue
        if path.is_dir():
            for file in path.rglob("*"):
                if file.is_file() and file.stat().st_mtime > built_at:
                    return True
        elif path.stat().st_mtime > built_at:
            return True
    return False


def _ensure_frontend_build(frontend_dir: Path) -> None:
    if _frontend_needs_build(frontend_dir):
        subprocess.run(
            "npm run build-only",
            cwd=str(frontend_dir),
            check=True,
            shell=True,
        )


def frontend() -> None:
    """Start the web dashboard (production preview by default)."""
    args = _frontend_parser().parse_args()
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if not (frontend_dir / "package.json").exists():
        print(f"Error: frontend directory not found at {frontend_dir}", file=sys.stderr)
        sys.exit(1)

    if args.dev:
        subprocess.run(
            "npm run dev",
            cwd=str(frontend_dir),
            check=True,
            shell=True,
        )
        return

    # Production: build when sources changed, then serve the built bundle.
    _ensure_frontend_build(frontend_dir)
    preview_args = []
    if args.host:
        preview_args.append(f"--host {args.host}")
    if args.port:
        preview_args.append(f"--port {args.port}")
    command = "npm run preview" + (
        " -- " + " ".join(preview_args) if preview_args else ""
    )
    subprocess.run(command, cwd=str(frontend_dir), check=True, shell=True)
