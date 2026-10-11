from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from schedflow.auth.security import AuthResult
from schedflow.core import Scheduler


def client(method="jwt"):
    from schedflow.agent import AgentConfig, AgentService
    from schedflow.api.routers.agent import router

    app = FastAPI()
    app.state.agent = AgentService(
        Scheduler(), config=AgentConfig(enabled=True, model="fake")
    )

    @app.middleware("http")
    async def actor(request: Request, call_next):
        if request.headers.get("x-actor"):
            request.state.auth = AuthResult(True, request.headers["x-actor"], method)
        return await call_next(request)

    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_missing_auth_is_denied_even_without_global_auth_middleware():
    c = client()
    assert c.get("/api/v1/agent/config-status").status_code == 200
    assert c.post("/api/v1/agent/sessions", json={}).status_code == 403


def test_actor_isolation_and_strict_api_requests():
    c = client()
    a = {"x-actor": "alice"}
    session = c.post("/api/v1/agent/sessions", json={}, headers=a).json()["data"]
    key = session["session_id"]
    assert (
        c.get("/api/v1/agent/sessions/" + key, headers={"x-actor": "bob"}).status_code
        == 404
    )
    assert (
        c.post("/api/v1/agent/sessions", json={"unexpected": 1}, headers=a).status_code
        == 422
    )
    detail = c.get("/api/v1/agent/sessions/" + key, headers=a).json()["data"]
    assert detail["messages"] == []
    assert detail["last_seq"] == 0


def test_api_key_cannot_confirm_proposal():
    c = client("apikey")
    assert (
        c.post(
            "/api/v1/agent/proposals/missing/approve",
            json={"proposal_version": 1},
            headers={"x-actor": "alice"},
        ).status_code
        == 403
    )


def test_turn_event_replay_closes_at_terminal_and_respects_cursor():
    c = client()
    svc = c.app.state.agent
    session = svc.repository.create_session("alice")
    turn = {
        "turn_id": "turn",
        "session_id": session["session_id"],
        "status": "completed",
    }
    svc.repository.put("turn", "alice", session["session_id"], turn)
    first = svc.repository.add_event(
        "alice", session["session_id"], "turn", "status", {"status": "running"}
    )
    svc.repository.add_event(
        "alice",
        session["session_id"],
        "turn",
        "turn.completed",
        {"status": "completed"},
    )
    response = c.get(
        "/api/v1/agent/turns/turn/events?after=" + str(first),
        headers={"x-actor": "alice"},
    )
    assert response.status_code == 200
    assert "turn.completed" in response.text
    assert "running" not in response.text
