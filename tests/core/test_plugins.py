"""Static component registry tests (replaces entry-point discovery)."""

from schedflow.core.plugins import EXECUTOR_PLUGINS, JOBSTORE_PLUGINS


def test_executor_plugin_set_is_stable() -> None:
    assert set(EXECUTOR_PLUGINS) == {
        "debug",
        "threadpool",
        "processpool",
        "asyncio",
        "gevent",
        "tornado",
        "twisted",
    }


def test_jobstore_plugin_set_is_stable() -> None:
    assert set(JOBSTORE_PLUGINS) == {"memory", "sqlalchemy", "redis", "mongodb"}


def test_executor_plugins_instantiate() -> None:
    for plugin_cls in EXECUTOR_PLUGINS.values():
        plugin_cls()


def test_jobstore_plugins_instantiate() -> None:
    for plugin_cls in JOBSTORE_PLUGINS.values():
        plugin_cls()
