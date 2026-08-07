"""CLI startup mode tests: production by default, dev only with --dev."""

import sys

from schedflow import cli
from schedflow.configs.settings import Settings, settings


def test_settings_default_to_production():
    """The shipped defaults must be production-safe (no reload watcher)."""
    s = Settings(_env_file=None)
    assert s.APP_ENV == "production"
    assert s.RELOAD is False
    assert s.LOG_LEVEL == "INFO"


def _capture_uvicorn_run(monkeypatch):
    calls = {}

    def fake_run(target, **kwargs):
        calls["target"] = target
        calls.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    return calls


def test_backend_defaults_to_production(monkeypatch):
    calls = _capture_uvicorn_run(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["schedflow-backend"])

    cli.backend()

    assert calls["reload"] is False
    assert calls["workers"] == 1
    assert calls["target"] is cli.app
    assert settings.RELOAD is False
    settings.RELOAD = False


def test_backend_dev_enables_reload(monkeypatch):
    calls = _capture_uvicorn_run(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["schedflow-backend", "--dev"])

    cli.backend()

    assert calls["reload"] is True
    assert calls["target"] == "schedflow.cli:app"
    assert calls["reload_excludes"]
    assert settings.RELOAD is True
    settings.RELOAD = False
    settings.LOG_LEVEL = "INFO"


def _capture_subprocess(monkeypatch):
    commands = []
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)),
    )
    return commands


def test_frontend_defaults_to_production_preview(monkeypatch):
    commands = _capture_subprocess(monkeypatch)
    monkeypatch.setattr(cli, "_ensure_frontend_build", lambda _d: None)
    monkeypatch.setattr(sys, "argv", ["schedflow-frontend"])

    cli.frontend()

    assert commands[-1][0] == "npm run preview"


def test_frontend_dev_uses_vite_dev_server(monkeypatch):
    commands = _capture_subprocess(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["schedflow-frontend", "--dev"])

    cli.frontend()

    assert len(commands) == 1
    assert commands[0][0] == "npm run dev"
