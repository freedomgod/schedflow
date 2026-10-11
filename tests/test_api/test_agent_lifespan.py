from fastapi.testclient import TestClient

from schedflow.api import create_app
from schedflow.core import Scheduler


class FakeAgent:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.events = []

    async def start(self):
        self.events.append("start")

    async def close(self):
        self.events.append("close")


def test_agent_lifecycle_reuses_the_only_scheduler():
    scheduler = Scheduler()
    agent = FakeAgent(scheduler)
    app = create_app(
        scheduler, agent_service=agent, include_routers=False, include_auth=False
    )
    assert app.state.agent is agent
    assert app.state.scheduler is app.state.scheduler_api is agent.scheduler
    with TestClient(app):
        assert agent.events == ["start"]
    assert agent.events == ["start", "close"]


def test_scheduler_stops_even_if_agent_cleanup_fails():
    scheduler = Scheduler()
    agent = FakeAgent(scheduler)

    async def fail_close():
        raise RuntimeError("cleanup failed")

    agent.close = fail_close
    app = create_app(
        scheduler, agent_service=agent, include_routers=False, include_auth=False
    )
    import pytest

    from schedflow.core.scheduler import STATE_STOPPED

    with pytest.raises(RuntimeError, match="cleanup failed"), TestClient(app):
        pass
    assert scheduler.state == STATE_STOPPED
