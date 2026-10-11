import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from schedflow.agent.config import AgentConfig
from schedflow.core import Scheduler


def profile(**changes):
    return {
        "provider": "custom",
        "protocol": "chat_completions",
        "base_url": "http://localhost:11434/v1",
        "model": "local",
        "enabled": True,
        **changes,
    }


def test_settings_key_preservation_and_destination_isolation():
    from schedflow.agent.settings import config_candidate, public_config

    current = AgentConfig(**profile(api_key="private-provider-token"))
    saved = config_candidate(current, profile(api_key=""))
    assert saved.api_key == current.api_key
    assert "private-provider-token" not in json.dumps(public_config(saved, "database"))
    assert public_config(saved, "database")["has_api_key"]
    with pytest.raises(ValueError, match="key"):
        config_candidate(current, profile(base_url="https://another.example/v1"))
    cleared = config_candidate(current, profile(clear_api_key=True))
    assert not cleared.api_key


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@host/v1",
        "https://host/v1?api_key=secret",
        "https://host/v1#secret",
        "file:///private",
        "https://{WorkspaceId}.host/v1",
    ],
)
def test_invalid_config_never_enables(url):
    from schedflow.agent.settings import config_candidate

    with pytest.raises(ValueError):
        config_candidate(AgentConfig(), profile(base_url=url))


def test_private_settings_restore_over_environment(monkeypatch):
    from schedflow.agent.settings import AgentSettings

    storage = AgentSettings()
    config = AgentConfig(**profile(api_key="private-key"))
    storage.save(config)
    monkeypatch.setenv("SCHEDFLOW_AGENT_MODEL", "environment-model")
    restored, source = storage.load(AgentConfig())
    assert source == "database"
    assert restored.model == "local"
    assert restored.api_key == "private-key"


@pytest.mark.parametrize("provider", ["kimi", "custom"])
@pytest.mark.parametrize(
    "model",
    ["kimi-k3", "kimi-k3-highspeed", "kimi-k2.7-code", "kimi-k2.7-code-highspeed"],
)
def test_forced_preserved_kimi_models_are_rejected_before_enabling(provider, model):
    from schedflow.agent.settings import config_candidate, validate_config

    values = profile(
        provider=provider,
        model=model,
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    with pytest.raises(ValueError, match=r"kimi-k2\.6"):
        validate_config(AgentConfig(**values))
    with pytest.raises(ValueError, match=r"kimi-k2\.6"):
        config_candidate(AgentConfig(), values)
    disabled = config_candidate(AgentConfig(), {**values, "enabled": False})
    assert not disabled.public_status()["configured"]


def test_legacy_enabled_kimi_k3_can_be_disabled_and_cannot_be_reenabled():
    from schedflow.agent.settings import config_candidate

    values = profile(
        provider="kimi",
        model="kimi-k3",
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    legacy = AgentConfig(**values)
    disabled = config_candidate(legacy, {**values, "enabled": False, "api_key": ""})
    assert not disabled.enabled
    assert disabled.model == legacy.model
    assert disabled.api_key == legacy.api_key
    assert not disabled.public_status()["configured"]
    with pytest.raises(ValueError, match=r"kimi-k2\.6"):
        config_candidate(disabled, {**values, "enabled": True, "api_key": ""})


def test_legacy_enabled_kimi_k3_settings_restore_as_unconfigured_without_changing_saved_values():
    from schedflow.agent.settings import AgentSettings

    storage = AgentSettings()
    legacy = AgentConfig(
        **profile(
            provider="kimi",
            model="kimi-k3",
            api_key="private-key",
            base_url="https://api.moonshot.cn/v1",
        )
    )
    storage.save(legacy)
    restored, source = storage.load(AgentConfig())
    assert source == "database"
    assert restored.enabled
    assert restored.model == legacy.model
    assert restored.api_key == legacy.api_key
    assert not restored.public_status()["configured"]


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "https://user:password@api.moonshot.cn/v1"},
        {"api_key": "private\nkey"},
    ],
)
def test_legacy_kimi_restore_still_rejects_unsafe_destination_or_key(changes):
    from schedflow.agent.settings import AgentSettings

    storage = AgentSettings()
    values = profile(
        provider="kimi",
        model="kimi-k3",
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    legacy = AgentConfig(**{**values, **changes})
    storage.save(legacy)
    with pytest.raises(ValueError, match="Stored Agent configuration is invalid"):
        storage.load(AgentConfig())


@pytest.mark.parametrize(
    "changes", [{"api_key": ""}, {"model": ""}, {"api_key": "private-key\n"}]
)
def test_enabled_legacy_kimi_restore_requires_real_valid_model_and_key(changes):
    from schedflow.agent.settings import AgentSettings

    storage = AgentSettings()
    values = profile(
        provider="kimi",
        model="kimi-k3",
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    storage.save(AgentConfig(**{**values, **changes}))
    with pytest.raises(ValueError, match="Stored Agent configuration is invalid"):
        storage.load(AgentConfig())


def test_disabled_unsupported_kimi_model_still_validates_destination_and_key():
    from schedflow.agent.settings import config_candidate

    values = profile(
        provider="kimi",
        model="kimi-k3",
        enabled=False,
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    with pytest.raises(ValueError, match="API root"):
        config_candidate(
            AgentConfig(),
            {**values, "base_url": "https://user:password@api.moonshot.cn/v1"},
        )
    with pytest.raises(ValueError, match="Invalid API key"):
        config_candidate(AgentConfig(), {**values, "api_key": "private\nkey"})


def test_kimi_k26_is_supported_without_silently_changing_model():
    from schedflow.agent.settings import config_candidate, validate_config

    values = profile(
        provider="kimi",
        model="kimi-k2.6",
        api_key="private-key",
        base_url="https://api.moonshot.cn/v1",
    )
    configured = config_candidate(AgentConfig(), values)
    validate_config(configured)
    assert configured.model == "kimi-k2.6"


def test_custom_nonmoonshot_relay_is_not_rejected_by_kimi_model_guard():
    from schedflow.agent.settings import validate_config

    validate_config(
        AgentConfig(**profile(model="kimi-k3", base_url="https://custom.example/v1"))
    )


@pytest.mark.asyncio
async def test_disable_cancels_queued_turn_and_blocks_new_approval():
    from schedflow.agent.service import AgentService

    class Provider:
        async def stream(self, messages, tools):
            await asyncio.sleep(10)
            yield {"type": "text", "text": "unexpected"}

    svc = AgentService(
        Scheduler(), config=AgentConfig(**profile()), provider=Provider()
    )
    session = svc.repository.create_session("alice")["session_id"]
    turn = await svc.submit_turn("alice", session, "hello")
    await svc.set_enabled(False)
    assert svc.repository.get("turn", "alice", turn["turn_id"])["status"] == "cancelled"
    assert all(t.done() for t in svc.tasks.values())
    with pytest.raises(ValueError, match="disabled"):
        await svc.submit_turn("alice", session, "hello")
    wf = __import__("schedflow.core", fromlist=["Workflow"]).Workflow()
    wf.add_task("a", "builtins:print")
    job = svc.scheduler.add_job(wf)
    proposal = svc.propose("alice", session, "update", {"name": "changed"}, job.job_id)
    with pytest.raises(ValueError, match="disabled"):
        svc.approve("alice", proposal["proposal_id"], 1)
    assert svc.scheduler.get_job(job.job_id).name != "changed"
    await svc.close()


@pytest.mark.asyncio
async def test_probe_uses_only_synthetic_data_and_keeps_config_unchanged():
    from schedflow.agent.settings import probe_config

    captured = []

    class Provider:
        async def stream(self, messages, tools):
            captured.append(messages.copy())
            if len(captured) == 1:
                yield {
                    "type": "tool_call",
                    "id": "test",
                    "name": "schedflow_connection_probe",
                    "arguments": '{"nonce":"connection-check"}',
                }
                yield {
                    "type": "assistant_message",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "opaque",
                        "tool_calls": [
                            {
                                "id": "test",
                                "type": "function",
                                "function": {
                                    "name": "schedflow_connection_probe",
                                    "arguments": '{"nonce":"connection-check"}',
                                },
                            }
                        ],
                    },
                }
            else:
                yield {"type": "text", "text": "OK"}

    cfg = AgentConfig(**profile(api_key="private-key"))
    result = await probe_config(cfg, lambda _: Provider())
    assert result["success"]
    assert captured[1][-2]["reasoning_content"] == "opaque"
    assert captured[1][-1]["content"] == '{"ok":true}'
    assert "private-key" not in json.dumps(captured)
    assert cfg.enabled


@pytest.mark.asyncio
async def test_probe_exception_redacts_candidate_key_and_url():
    from schedflow.agent.settings import probe_config

    class Provider:
        async def stream(self, messages, tools):
            raise RuntimeError(
                "private-key in Authorization https://private.example/v1"
            )
            yield

    result = await probe_config(
        AgentConfig(**profile(api_key="private-key")), lambda _: Provider()
    )
    assert not result["success"]
    assert "private-key" not in str(result)
    assert "private.example" not in str(result)


@pytest.mark.asyncio
async def test_live_configuration_waits_for_old_turn_before_closing_connection(
    monkeypatch,
):
    import schedflow.agent.service as service_module
    from schedflow.agent.service import AgentService

    entered = asyncio.Event()
    order = []

    class OldProvider:
        async def stream(self, messages, tools):
            entered.set()
            try:
                await asyncio.Event().wait()
                yield {"type": "text", "text": "unexpected"}
            finally:
                order.append(("stream_cleanup", svc.config.base_url))

        async def close(self):
            order.append(
                (
                    "close",
                    svc.repository.get("turn", "alice", turn["turn_id"])["status"],
                )
            )

    svc = AgentService(
        Scheduler(),
        config=AgentConfig(**profile(api_key="old-private-key")),
        provider=OldProvider(),
    )
    session = svc.repository.create_session("alice")["session_id"]
    finalize = svc.repository.finalize_turn

    def record_finalize(*args, **kwargs):
        order.append(("finalize", svc.config.base_url))
        return finalize(*args, **kwargs)

    monkeypatch.setattr(svc.repository, "finalize_turn", record_finalize)
    turn = await svc.submit_turn("alice", session, "hello")
    await asyncio.wait_for(entered.wait(), 3)
    monkeypatch.setattr(
        service_module, "create_provider", lambda cfg: SimpleNamespace(config=cfg)
    )
    changed = await svc.configure(
        profile(base_url="https://new.example/v1", api_key="new-private-key")
    )
    assert changed["base_url"] == "https://new.example/v1"
    assert order[-1] == ("close", "cancelled")
    assert ("stream_cleanup", "http://localhost:11434/v1") in order
    assert all(
        url == "http://localhost:11434/v1"
        for phase, url in order
        if phase == "finalize"
    )
    snapshot = svc.repository.get_session("alice", session)
    assert snapshot["turns"][-1]["status"] == "cancelled"
    assert all(message["status"] != "streaming" for message in snapshot["messages"])
    assert "old-private-key" not in json.dumps(snapshot)
    assert "new-private-key" not in json.dumps(snapshot)
    await svc.close()


@pytest.mark.asyncio
async def test_start_restores_saved_config_instead_of_environment(monkeypatch):
    from schedflow.agent.service import AgentService
    from schedflow.agent.settings import AgentSettings

    AgentSettings().save(AgentConfig(**profile(api_key="private-key")))
    monkeypatch.setenv("SCHEDFLOW_AGENT_MODEL", "environment-model")
    svc = AgentService(Scheduler())
    await svc.start()
    assert svc.config.model == "local"
    assert svc.config_source == "database"
    assert svc.provider.config.api_key == "private-key"
    await svc.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,value",
    [
        ("SCHEDFLOW_AGENT_PROTOCOL", "invalid"),
        ("SCHEDFLOW_AGENT_TIMEOUT", "invalid-number"),
    ],
)
async def test_saved_config_wins_over_invalid_environment(monkeypatch, name, value):
    from schedflow.agent.service import AgentService
    from schedflow.agent.settings import AgentSettings

    AgentSettings().save(AgentConfig(**profile(api_key="private-key")))
    monkeypatch.setenv(name, value)
    svc = AgentService(Scheduler())
    await svc.start()
    assert svc.config.protocol == "chat_completions"
    assert svc.config.timeout == 60
    assert svc.config_source == "database"
    await svc.close()


@pytest.mark.asyncio
async def test_unsafe_environment_destination_cannot_submit_a_turn():
    from schedflow.agent.service import AgentService

    class Provider:
        async def stream(self, messages, tools):
            raise AssertionError("Unsafe destination must not reach a provider")
            yield

    svc = AgentService(
        Scheduler(),
        config=AgentConfig(**profile(base_url="https://host/v1?api_key=private-key")),
        provider=Provider(),
    )
    session = svc.repository.create_session("alice")["session_id"]
    with pytest.raises(ValueError, match="root"):
        await svc.submit_turn("alice", session, "hello")
    assert not svc.tasks
    await svc.close()


@pytest.mark.asyncio
async def test_settings_api_human_only_and_validation_never_echoes_key():
    from fastapi import FastAPI

    from schedflow.agent.service import AgentService
    from schedflow.api.routers.agent import router

    app = FastAPI()
    svc = AgentService(Scheduler(), config=AgentConfig())
    app.state.agent = svc
    app.include_router(router, prefix="/api/v1")
    method = "api_key"

    @app.middleware("http")
    async def actor(request, call_next):
        request.state.auth = SimpleNamespace(
            success=True, user_id="alice", method=method
        )
        return await call_next(request)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/agent/config")).status_code == 403
        assert (
            await client.put("/api/v1/agent/enabled", json={"enabled": True})
        ).status_code == 403
        method = "jwt"
        body = profile(api_key="private-secret-key")
        result = await client.put("/api/v1/agent/config", json=body)
        assert result.status_code == 200
        assert "private-secret-key" not in result.text
        assert (await client.get("/api/v1/agent/config")).json()["data"][
            "source"
        ] == "database"
        body["max_steps"] = "private-secret-key"
        invalid = await client.put("/api/v1/agent/config", json=body)
        assert invalid.status_code == 422
        assert "private-secret-key" not in invalid.text
    await svc.close()
