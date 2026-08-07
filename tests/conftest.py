from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import pytz
import redis

from schedflow.configs.settings import settings
from schedflow.utils import localize

SERVICE_CONFIG = {
    "redis": {
        "host": settings.SCHEDFLOW_REDIS_HOST,
        "port": settings.SCHEDFLOW_REDIS_PORT,
        "username": settings.SCHEDFLOW_REDIS_USERNAME,
        "password": settings.SCHEDFLOW_REDIS_PASSWORD,
        "db": settings.SCHEDFLOW_REDIS_DB,
    },
    "mongodb": {
        "host": settings.SCHEDFLOW_MONGODB_HOST,
        "port": settings.SCHEDFLOW_MONGODB_PORT,
        "username": settings.SCHEDFLOW_MONGODB_USERNAME,
        "password": settings.SCHEDFLOW_MONGODB_PASSWORD,
        "auth_source": settings.SCHEDFLOW_MONGODB_AUTH_SOURCE,
    },
}

def pytest_configure(config):
    # 注册自定义标记
    config.addinivalue_line("markers", "redis: 需要 Redis 服务的测试")
    config.addinivalue_line("markers", "integration: 集成测试 - 验证组件间交互")
    config.addinivalue_line("markers", "e2e: 端到端测试 - 验证完整工作流")
    config.addinivalue_line("markers", "slow: 运行缓慢的测试")
    config.addinivalue_line("markers", "external: 需要外部服务的测试")


def is_redis_available():
    """检测 Redis 是否可用"""
    try:
        cfg = SERVICE_CONFIG["redis"]
        kwargs = {"host": cfg["host"], "port": cfg["port"], "socket_timeout": 1}
        if cfg.get("username"):
            kwargs["username"] = cfg["username"]
        if cfg.get("password"):
            kwargs["password"] = cfg["password"]
        r = redis.Redis(**kwargs)
        return r.ping()
    except (redis.ConnectionError, redis.TimeoutError, ConnectionRefusedError):
        return False


def pytest_collection_modifyitems(config, items):
    """根据服务可用性自动跳过测试"""
    if not hasattr(config, "cache"):
        return

    redis_ok = getattr(config, "_redis_available", None)
    if redis_ok is None:
        redis_ok = is_redis_available()
        config._redis_available = redis_ok

    skip_redis = pytest.mark.skip(reason="Redis 服务不可用")

    for item in items:
        is_redis_test = any("redis" in kw for kw in item.keywords)
        if is_redis_test and not redis_ok:
            item.add_marker(skip_redis)


@pytest.fixture(autouse=True)
def isolated_meta_db(tmp_path, monkeypatch):
    """Redirect the metadata DB to a temporary file for every test.

    Tests must never touch the real runtime database (``scheduler_meta.db``):
    previously, test cleanup deleted that file, which silently wiped the
    registered admin account and left test data behind.
    """
    import schedflow.auth.models as auth_models
    import schedflow.auth.services as auth_services
    import schedflow.configs.config as config_module

    db_path = tmp_path / "scheduler_meta.db"
    monkeypatch.setattr(settings, "SCHEDFLOW_META_DB", str(db_path))
    monkeypatch.setattr(config_module, "DEFAULT_META_DB", db_path)
    monkeypatch.setattr(auth_models, "META_DB", str(db_path))
    auth_services.SECRET_KEY_CACHE = None
    yield
    auth_services.SECRET_KEY_CACHE = None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(params=["pytz", "zoneinfo"])
def timezone(request):
    if request.param == "pytz":
        return pytz.timezone("Europe/Berlin")
    return ZoneInfo("Europe/Berlin")


@pytest.fixture
def freeze_time(monkeypatch, timezone):
    class TimeFreezer:
        def __init__(self, initial):
            self.current = initial
            self.increment = None

        def get(self, tzinfo=None):
            now = (
                self.current.astimezone(tzinfo)
                if tzinfo
                else self.current.replace(tzinfo=None)
            )
            if self.increment:
                self.current += self.increment
            return now

        def set(self, new_time):
            self.current = new_time

        def next(self):
            return self.current + self.increment

        def set_increment(self, delta):
            self.increment = delta

    freezer = TimeFreezer(localize(datetime(2011, 4, 3, 18, 40), timezone))  # noqa: DTZ001
    fake_datetime = Mock(datetime, now=freezer.get)
    monkeypatch.setattr("schedflow.triggers.interval.datetime", fake_datetime)
    monkeypatch.setattr("schedflow.triggers.date.datetime", fake_datetime)
    return freezer
