import asyncio
import json

import httpx
import pytest

from schedflow.core import Scheduler, Workflow


def config(**kwargs):
    from schedflow.agent import AgentConfig

    return AgentConfig(enabled=True, model="local", **kwargs)


def service(**kwargs):
    from schedflow.agent import AgentService

    return AgentService(
        Scheduler(), config=config(allow_code_generation=True), **kwargs
    )


def candidate():
    return {
        "name": "hello",
        "workflow": {
            "nodes": [
                {
                    "node_id": "a",
                    "task": {"type": "python_script", "script": "print(42)"},
                }
            ]
        },
    }


def test_config_disabled_and_key_never_public():
    from schedflow.agent import AgentConfig

    cfg = AgentConfig(api_key="private-token")
    assert not cfg.enabled
    assert "private-token" not in str(cfg.public_status())
    cfg.base_url = "https://user:pass@example.com/v1?key=secret"
    assert cfg.public_status()["base_url"] == "https://example.com/v1"


def test_existing_code_can_be_managed_but_new_executable_reference_requires_opt_in():
    from schedflow.agent import AgentService

    svc = AgentService(Scheduler(), config=config())
    session = svc.repository.create_session("alice")
    wf = Workflow()
    wf.add_task("a", "builtins:print")
    job = svc.scheduler.add_job(wf)
    p = svc.propose(
        "alice", session["session_id"], "update", {"name": "allowed"}, job.job_id
    )
    assert p["after"]["name"] == "allowed"
    changed = job.to_dict()["workflow"]
    changed["nodes"][0]["task"]["ref"] = "arbitrary:code"
    with pytest.raises(ValueError):
        svc.propose(
            "alice", session["session_id"], "update", {"workflow": changed}, job.job_id
        )
    copied = job.to_dict()["workflow"]
    copied["project_root"] = "another_project"
    with pytest.raises(ValueError):
        svc.propose("alice", session["session_id"], "create", {"workflow": copied})


def test_confirmation_exact_code_and_credentials_rejected():
    svc = service()
    session = svc.repository.create_session("alice")
    data = candidate()
    data["workflow"]["nodes"][0]["task"]["script"] = (
        "# long script\n" + ("# comment\n" * 2000) + "print(42)"
    )
    p = svc.propose("alice", session["session_id"], "create", data)
    assert (
        p["after"]["workflow"]["nodes"][0]["task"]["script"]
        == data["workflow"]["nodes"][0]["task"]["script"]
    )
    svc.config.api_key = "very-secret-provider-key"
    data["name"] = svc.config.api_key
    with pytest.raises(ValueError):
        svc.propose("alice", session["session_id"], "create", data)


def test_delete_session_retains_dedup_receipts():
    svc = service()
    session = svc.repository.create_session("alice")
    p = svc.propose("alice", session["session_id"], "create", candidate())
    op = svc.approve("alice", p["proposal_id"], 1)
    svc.repository.delete_session("alice", session["session_id"])
    assert (
        svc.get_operation("alice", op["operation_id"])["operation_id"]
        == op["operation_id"]
    )
    assert (
        svc.approve("alice", p["proposal_id"], 1)["operation_id"] == op["operation_id"]
    )


def test_unknown_create_reconciles_by_hash_without_retry():
    svc = service()
    session = svc.repository.create_session("alice")
    p = svc.propose("alice", session["session_id"], "create", candidate())
    op = svc.approve("alice", p["proposal_id"], 1)
    internal = svc.repository.get("operation", "alice", op["operation_id"])
    internal["status"] = "unknown"
    svc.repository.put("operation", "alice", session["session_id"], internal)
    assert svc.get_operation("alice", op["operation_id"])["status"] == "succeeded"
    assert len(svc.scheduler.get_jobs()) == 1


def test_value_error_after_store_commit_is_uncertain_then_reconciled(monkeypatch):
    svc = service()
    session = svc.repository.create_session("alice")
    p = svc.propose("alice", session["session_id"], "create", candidate())
    store = svc.scheduler.get_jobstore("default")
    original = store.add

    def commit_then_fail(job):
        original(job)
        raise ValueError("transport result lost")

    monkeypatch.setattr(store, "add", commit_then_fail)
    with pytest.raises(ValueError):
        svc.approve("alice", p["proposal_id"], 1)
    operation = svc.repository.list("operation", "alice", session["session_id"])[0]
    assert operation["status"] == "unknown"
    assert (
        svc.get_operation("alice", operation["operation_id"])["status"] == "succeeded"
    )
    assert len(svc.scheduler.get_jobs()) == 1


@pytest.mark.asyncio
async def test_split_secret_heuristic_never_leaks_suffix():
    class Provider:
        async def stream(self, messages, tools):
            yield {"type": "text", "text": "sk-abcdefghijklmnop"}
            yield {"type": "text", "text": "qrstuvwxyz"}

    svc = service(provider=Provider())
    svc.config.api_key = "sk-abcdefghijklmnopqrstuvwxyz"
    session = svc.repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "hello")
    await svc.wait_turn(turn["turn_id"])
    assert "qrstuvwxyz" not in json.dumps(
        svc.repository.get_session("alice", session["session_id"])
    )


@pytest.mark.asyncio
async def test_provider_rejects_abrupt_stream():
    from schedflow.agent.provider import ChatCompletionsProvider

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            )
        )
    )
    provider = ChatCompletionsProvider(config(), client=client)
    with pytest.raises(ValueError):
        _ = [e async for e in provider.stream([], [])]
    await client.aclose()


def test_repository_actor_isolation_and_event_recovery():
    from schedflow.agent.repository import AgentRepository

    repo = AgentRepository()
    session = repo.create_session("alice")
    assert repo.get_session("bob", session["session_id"]) is None
    repo.add_event(
        "alice", session["session_id"], "turn", "status", {"status": "running"}
    )
    assert len(repo.events("alice", session["session_id"], 0)) == 1
    assert repo.events("alice", session["session_id"], 1) == []
    assert repo.events("bob", session["session_id"], 0) == []


def test_proposals_paused_immutable_deduplicated_and_revised():
    svc = service()
    session = svc.repository.create_session("alice")
    proposal = svc.propose("alice", session["session_id"], "create", candidate())
    assert proposal["after"]["status"] == "paused"
    assert not svc.scheduler.get_jobs()
    with pytest.raises(ValueError):
        svc.approve("alice", proposal["proposal_id"], 9)
    revised = svc.revise("alice", proposal["proposal_id"], enabled=True)
    assert revised["version"] == 2
    with pytest.raises(ValueError):
        svc.approve("alice", proposal["proposal_id"], 1)
    op = svc.approve("alice", proposal["proposal_id"], 2)
    assert (
        svc.approve("alice", proposal["proposal_id"], 2)["operation_id"]
        == op["operation_id"]
    )
    assert len(svc.scheduler.get_jobs()) == 1
    assert op["status"] == "succeeded"


def test_unknown_nested_fields_and_code_generation_are_rejected():
    from schedflow.agent import AgentService

    svc = AgentService(Scheduler(), config=config())
    session = svc.repository.create_session("alice")
    with pytest.raises(ValueError):
        svc.propose("alice", session["session_id"], "create", candidate())
    data = candidate()
    data["workflow"]["nodes"][0]["task"]["surprise"] = True
    with pytest.raises(ValueError):
        service().propose("alice", session["session_id"], "create", data)


def test_stale_update_and_actor_cannot_approve():
    svc = service()
    session = svc.repository.create_session("alice")
    wf = Workflow()
    wf.add_task("a", "builtins:print")
    job = svc.scheduler.add_job(wf, name="before")
    p = svc.propose(
        "alice", session["session_id"], "update", {"name": "after"}, job.job_id
    )
    with pytest.raises(KeyError):
        svc.approve("bob", p["proposal_id"], 1)
    svc.scheduler.update_job(job.job_id, name="concurrent")
    with pytest.raises(ValueError):
        svc.approve("alice", p["proposal_id"], 1)
    assert svc.scheduler.get_job(job.job_id).name == "concurrent"


def test_proposal_base_hash_is_derived_from_its_exact_before_snapshot(monkeypatch):
    from schedflow.core.commands import config_hash

    svc = service()
    session = svc.repository.create_session("alice")
    wf = Workflow()
    wf.add_task("a", "builtins:print")
    job = svc.scheduler.add_job(wf, name="before")

    def racing_hash(job_id):
        svc.scheduler.update_job(job_id, name="raced")
        return config_hash(svc.scheduler.get_job(job_id).to_dict())

    monkeypatch.setattr(svc.scheduler, "job_config_hash", racing_hash)
    p = svc.propose(
        "alice", session["session_id"], "update", {"description": "new"}, job.job_id
    )
    assert p["expected_hash"] == config_hash(p["before"])


@pytest.mark.asyncio
async def test_provider_assembles_tool_deltas_by_index_and_redacts_errors():
    from schedflow.agent.provider import ChatCompletionsProvider

    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "content": "Hi",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call1",
                                "function": {
                                    "name": "list_workflows",
                                    "arguments": "{",
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"arguments": "}"}}]
                    }
                }
            ]
        },
    ]

    async def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            text="".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
            + "data: [DONE]\n\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ChatCompletionsProvider(config(api_key="secret"), client=client)
    events = [e async for e in provider.stream([], [])]
    assert events[0] == {"type": "text", "text": "Hi"}
    assert events[-1]["arguments"] == "{}"
    assert events[-1]["name"] == "list_workflows"
    await client.aclose()


@pytest.mark.asyncio
async def test_bounded_loop_persists_blocks_and_never_allows_approval_tool():
    class Provider:
        async def stream(self, messages, tools):
            yield {"type": "tool_call", "id": "x", "name": "approve", "arguments": "{}"}

    svc = service(provider=Provider())
    svc.config.max_steps = 2
    session = svc.repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "make something")
    await svc.wait_turn(turn["turn_id"])
    detail = svc.repository.get_session("alice", session["session_id"])
    assert detail["turns"][0]["status"] == "failed"
    assert detail["messages"][-1]["blocks"][-1]["type"] == "error"
    assert not svc.scheduler.get_jobs()
    assert (
        svc.repository.events("alice", session["session_id"], 0)[-1]["type"]
        == "turn.failed"
    )


@pytest.mark.asyncio
async def test_actual_run_has_background_receipt_and_log():
    svc = service()
    await svc.start()
    session = svc.repository.create_session("alice")
    p = svc.propose("alice", session["session_id"], "create", candidate())
    created = svc.approve("alice", p["proposal_id"], 1)
    p = svc.propose("alice", session["session_id"], "run", {}, created["job_id"])
    op = svc.approve("alice", p["proposal_id"], 1)
    assert op["execution_id"]
    for _ in range(100):
        current = svc.get_operation("alice", op["operation_id"])
        if current["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert current["status"] == "succeeded"
    assert current["result"]["log_id"] == op["execution_id"]
    await svc.close()


def test_query_projection_preview_and_clarification_blocks():
    svc = service()
    session = svc.repository.create_session("alice")
    wf = Workflow()
    wf.add_task("a", type="python_script", script='print("private source")')
    job = svc.scheduler.add_job(wf)
    result, _ = svc._tool(
        "alice",
        session["session_id"],
        "turn",
        {"name": "get_workflow", "arguments": json.dumps({"job_id": job.job_id})},
    )
    assert "private source" not in json.dumps(result)
    result, _ = svc._tool(
        "alice",
        session["session_id"],
        "turn",
        {
            "name": "preview_schedule",
            "arguments": json.dumps(
                {"trigger": {"type": "interval", "args": {"minutes": 5}}, "count": 3}
            ),
        },
    )
    assert len(result["next_run_times"]) == 3
    _, block = svc._tool(
        "alice",
        session["session_id"],
        "turn",
        {
            "name": "ask_clarification",
            "arguments": json.dumps(
                {
                    "text": "启用吗?",
                    "options": [{"label": "保持暂停", "value": "paused"}],
                }
            ),
        },
    )
    assert block["type"] == "clarification"


@pytest.mark.asyncio
async def test_streaming_snapshot_matches_cursor_and_redacts_split_secret():
    class Provider:
        async def stream(self, messages, tools):
            yield {"type": "text", "text": "a" * 300 + " secret-"}
            yield {"type": "text", "text": "token"}

    svc = service(provider=Provider())
    svc.config.api_key = "secret-token"
    session = svc.repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "hello")
    await svc.wait_turn(turn["turn_id"])
    detail = svc.repository.get_session("alice", session["session_id"])
    events = svc.repository.events("alice", session["session_id"], 0)
    assert detail["last_seq"] == events[-1]["seq"]
    assert "secret-token" not in json.dumps(events)
    assert "[REDACTED]" in detail["messages"][-1]["blocks"][0]["text"]


def test_retention_erases_history_but_keeps_receipts():
    svc = service()
    session = svc.repository.create_session("alice")
    p = svc.propose("alice", session["session_id"], "create", candidate())
    op = svc.approve("alice", p["proposal_id"], 1)
    session.update(
        created_at="2000-01-01T00:00:00+00:00", updated_at="2000-01-01T00:00:00+00:00"
    )
    svc.repository.put("session", "alice", session["session_id"], session)
    svc.repository.cleanup(30)
    assert svc.repository.get_session("alice", session["session_id"]) is None
    assert (
        svc.get_operation("alice", op["operation_id"])["operation_id"]
        == op["operation_id"]
    )


def test_message_blocks_reject_arbitrary_client_html():
    from schedflow.agent.schemas import AgentMessage

    with pytest.raises(ValueError):
        AgentMessage.model_validate(
            {
                "message_id": "x",
                "role": "assistant",
                "status": "completed",
                "blocks": [{"type": "html", "html": "<button>approve</button>"}],
            }
        )


@pytest.mark.asyncio
async def test_immediate_cancel_persists_terminal_state_before_task_starts():
    class Provider:
        async def stream(self, messages, tools):
            await asyncio.sleep(1)
            yield {"type": "text", "text": "late"}

    svc = service(provider=Provider())
    session = svc.repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "hello")
    svc.cancel("alice", turn["turn_id"])
    await asyncio.sleep(0)
    assert svc.repository.get("turn", "alice", turn["turn_id"])["status"] == "cancelled"
    assert (
        svc.repository.events("alice", session["session_id"], 0)[-1]["type"]
        == "turn.completed"
    )


def test_reboot_marks_streaming_message_interrupted_with_terminal_event():
    svc = service()
    session = svc.repository.create_session("alice")
    svc.repository.put(
        "turn",
        "alice",
        session["session_id"],
        {"turn_id": "t", "session_id": session["session_id"], "status": "running"},
    )
    svc.repository.put(
        "message",
        "alice",
        session["session_id"],
        {
            "message_id": "m",
            "turn_id": "t",
            "role": "assistant",
            "status": "streaming",
            "blocks": [{"type": "assistant_text", "text": "partial"}],
        },
    )
    svc.repository.recover()
    detail = svc.repository.get_session("alice", session["session_id"])
    assert detail["messages"][0]["status"] == "interrupted"
    assert (
        svc.repository.events("alice", session["session_id"], 0)[-1]["type"]
        == "turn.failed"
    )


def test_new_proposal_for_same_workflow_supersedes_previous_candidate():
    svc = service()
    session = svc.repository.create_session("alice")
    initial = svc.propose("alice", session["session_id"], "create", candidate())
    created = svc.approve("alice", initial["proposal_id"], 1)
    old = svc.propose(
        "alice", session["session_id"], "update", {"name": "old"}, created["job_id"]
    )
    new = svc.propose(
        "alice", session["session_id"], "update", {"name": "new"}, created["job_id"]
    )
    assert (
        svc.repository.get("proposal", "alice", old["proposal_id"])["status"]
        == "superseded"
    )
    with pytest.raises(ValueError):
        svc.approve("alice", old["proposal_id"], 1)
    svc.approve("alice", new["proposal_id"], 1)
    assert svc.scheduler.get_job(created["job_id"]).name == "new"


def test_bounded_log_projection_retains_root_failure():
    svc = service()
    records = {"first": {"node_id": "first", "status": "failed", "error": "root cause"}}
    records.update(
        {str(i): {"node_id": str(i), "status": "skipped"} for i in range(99)}
    )
    summary = svc._model_run({"records": records})
    assert summary["records"][0]["error"] == "root cause"
    assert summary["omitted_records"] == 80
    assert summary["status_counts"] == {"failed": 1, "skipped": 99}


def test_provider_tool_parameters_have_resolvable_json_schema_refs():
    svc = service()

    def check(schema, root):
        if isinstance(schema, dict):
            if "$ref" in schema:
                current = root
                for part in schema["$ref"].removeprefix("#/").split("/"):
                    assert part in current, schema["$ref"]
                    current = current[part]
            for value in schema.values():
                check(value, root)
        elif isinstance(schema, list):
            for value in schema:
                check(value, root)

    for tool in svc.tools():
        parameters = tool["function"]["parameters"]
        check(parameters, parameters)


@pytest.mark.asyncio
async def test_initial_history_is_trimmed_before_provider_context_budget():
    class Provider:
        captured = None

        async def stream(self, messages, tools):
            self.captured = messages
            yield {"type": "text", "text": "ok"}

    provider = Provider()
    svc = service(provider=provider)
    session = svc.repository.create_session("alice")
    for index in range(19):
        svc.repository.put(
            "message",
            "alice",
            session["session_id"],
            {
                "message_id": str(index),
                "role": "user" if index % 2 == 0 else "assistant",
                "status": "completed",
                "blocks": [{"type": "assistant_text", "text": "x" * 16000}],
            },
        )
    turn = await svc.submit_turn("alice", session["session_id"], "current request")
    await svc.wait_turn(turn["turn_id"])
    assert sum(len(json.dumps(m)) for m in provider.captured) <= 120000
    assert provider.captured[-1]["content"] == "current request"


@pytest.mark.asyncio
async def test_terminal_turn_message_and_events_rollback_as_one_commit(tmp_path):
    import sqlite3

    from schedflow.agent.repository import AgentRepository

    class Connection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if (
                sql.startswith("INSERT INTO agent_events")
                and len(parameters) > 3
                and parameters[3] == "turn.completed"
            ):
                raise RuntimeError("simulated crash before terminal event commit")
            return super().execute(sql, parameters)

    repository = AgentRepository(
        lambda: sqlite3.connect(tmp_path / "atomic.db", factory=Connection)
    )

    class Provider:
        async def stream(self, messages, tools):
            yield {"type": "text", "text": "answer"}

    svc = service(repository=repository, provider=Provider())
    session = repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "hello")
    with pytest.raises(RuntimeError):
        await svc.wait_turn(turn["turn_id"])
    snapshot = repository.get_session("alice", session["session_id"])
    assert snapshot["turns"][0]["status"] == "running"
    assert snapshot["messages"][-1]["status"] == "streaming"


def test_explicit_draft_revision_preserves_identity_source_and_invalidates_old_version():
    svc = service()
    session = svc.repository.create_session("alice")
    original = svc.propose("alice", session["session_id"], "create", candidate())
    revised = svc.propose(
        "alice",
        session["session_id"],
        "create",
        {"name": "revised"},
        revises_proposal_id=original["proposal_id"],
    )
    assert revised["version"] == 2
    assert revised["job_id"] == original["job_id"]
    assert revised["payload"]["workflow"] == original["payload"]["workflow"]
    assert (
        svc.repository.get("proposal", "alice", original["proposal_id"])["status"]
        == "superseded"
    )
    with pytest.raises(ValueError):
        svc.approve("alice", original["proposal_id"], 1)
    svc.approve("alice", revised["proposal_id"], 2)
    assert svc.scheduler.get_job(revised["job_id"]).name == "revised"


def test_draft_revision_requires_pending_actor_session_action_and_job_identity():
    svc = service()
    session = svc.repository.create_session("alice")
    original = svc.propose("alice", session["session_id"], "create", candidate())
    separate = svc.propose("alice", session["session_id"], "create", candidate())
    assert (
        svc.repository.get("proposal", "alice", original["proposal_id"])["status"]
        == "awaiting_confirmation"
    )
    assert separate["job_id"] != original["job_id"]
    other = svc.repository.create_session("alice")
    bob = svc.repository.create_session("bob")
    for actor, target_session in [("alice", other), ("bob", bob)]:
        with pytest.raises((KeyError, ValueError)):
            svc.propose(
                actor,
                target_session["session_id"],
                "create",
                {"name": "revision"},
                revises_proposal_id=original["proposal_id"],
            )
    with pytest.raises(ValueError):
        svc.propose(
            "alice",
            session["session_id"],
            "create",
            {"job_id": "changed"},
            revises_proposal_id=original["proposal_id"],
        )
    svc.reject("alice", original["proposal_id"])
    with pytest.raises(ValueError):
        svc.propose(
            "alice",
            session["session_id"],
            "create",
            {},
            revises_proposal_id=original["proposal_id"],
        )


@pytest.mark.asyncio
async def test_followup_provider_receives_draft_context_and_can_read_proposal():
    class Provider:
        captured = None

        async def stream(self, messages, tools):
            self.captured = messages
            yield {"type": "text", "text": "ok"}

    provider = Provider()
    svc = service(provider=provider)
    session = svc.repository.create_session("alice")
    draft = svc.propose("alice", session["session_id"], "create", candidate())
    turn = await svc.submit_turn("alice", session["session_id"], "把刚才的草案改个名字")
    await svc.wait_turn(turn["turn_id"])
    context = json.dumps(provider.captured)
    assert draft["proposal_id"] in context
    assert draft["job_id"] in context
    assert "revises_proposal_id" in context
    result, _ = svc._tool(
        "alice",
        session["session_id"],
        "turn",
        {
            "name": "get_proposal",
            "arguments": json.dumps({"proposal_id": draft["proposal_id"]}),
        },
    )
    assert result["proposal_id"] == draft["proposal_id"]
    assert "print(42)" not in json.dumps(result)


@pytest.mark.asyncio
async def test_two_model_turns_revise_create_schedule_through_explicit_draft_tool():
    class Provider:
        proposal_id = None

        async def stream(self, messages, tools):
            if messages[-1]["role"] == "tool":
                yield {"type": "text", "text": "请确认草案"}
                return
            if self.proposal_id is None:
                payload = candidate()
                payload["trigger"] = {"type": "cron", "args": {"hour": 8}}
                arguments = {"payload": payload}
            else:
                assert self.proposal_id in json.dumps(messages)
                create_tool = next(
                    t["function"]
                    for t in tools
                    if t["function"]["name"] == "propose_create_workflow"
                )
                assert "revises_proposal_id" in create_tool["parameters"]["properties"]
                arguments = {
                    "payload": {"trigger": {"type": "cron", "args": {"hour": 9}}},
                    "revises_proposal_id": self.proposal_id,
                }
            yield {
                "type": "tool_call",
                "id": "draft",
                "name": "propose_create_workflow",
                "arguments": json.dumps(arguments),
            }

    provider = Provider()
    svc = service(provider=provider)
    session = svc.repository.create_session("alice")
    first_turn = await svc.submit_turn(
        "alice", session["session_id"], "创建每天8点工作流"
    )
    await svc.wait_turn(first_turn["turn_id"])
    first = svc.repository.list("proposal", "alice", session["session_id"])[0]
    provider.proposal_id = first["proposal_id"]
    second_turn = await svc.submit_turn(
        "alice", session["session_id"], "把刚才草案改到9点"
    )
    await svc.wait_turn(second_turn["turn_id"])
    proposals = svc.repository.list("proposal", "alice", session["session_id"])
    assert proposals[0]["status"] == "superseded"
    assert proposals[1]["version"] == 2
    assert proposals[1]["job_id"] == first["job_id"]
    assert proposals[1]["payload"]["workflow"] == first["payload"]["workflow"]
    assert str(proposals[1]["payload"]["trigger"]["args"]["hour"]) == "9"
    with pytest.raises(ValueError):
        svc.approve("alice", first["proposal_id"], 1)
    assert svc.approve("alice", proposals[1]["proposal_id"], 2)["status"] == "succeeded"


@pytest.mark.asyncio
async def test_draft_context_has_aggregate_budget_preserving_all_draft_ids():
    class Provider:
        captured = None

        async def stream(self, messages, tools):
            self.captured = messages
            yield {"type": "text", "text": "ok"}

    provider = Provider()
    svc = service(provider=provider)
    session = svc.repository.create_session("alice")
    ids = []
    for index in range(5):
        data = {
            "workflow": {
                "nodes": [
                    {
                        "node_id": str(n),
                        "task": {
                            "type": "python_callable",
                            "ref": "module:" + ("f" * 1990),
                        },
                    }
                    for n in range(20)
                ]
            }
        }
        ids.append(
            svc.propose("alice", session["session_id"], "create", data)["proposal_id"]
        )
    turn = await svc.submit_turn("alice", session["session_id"], "修改刚才的草案")
    await svc.wait_turn(turn["turn_id"])
    assert sum(len(json.dumps(m)) for m in provider.captured) <= 120000
    assert all(key in json.dumps(provider.captured) for key in ids)


@pytest.mark.asyncio
async def test_active_cancel_terminal_snapshot_is_already_coherent():
    entered = asyncio.Event()

    class Provider:
        async def stream(self, messages, tools):
            entered.set()
            await asyncio.sleep(1)
            yield {"type": "text", "text": "late"}

    svc = service(provider=Provider())
    session = svc.repository.create_session("alice")
    turn = await svc.submit_turn("alice", session["session_id"], "hello")
    await entered.wait()
    svc.cancel("alice", turn["turn_id"])
    snapshot = svc.repository.get_session("alice", session["session_id"])
    assert snapshot["turns"][0]["status"] == "cancelled"
    assert snapshot["messages"][-1]["status"] == "cancelled"
    await svc.wait_turn(turn["turn_id"])
