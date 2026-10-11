import asyncio

import pytest


@pytest.mark.asyncio
async def test_real_graph_routes_opaque_assistant_and_tool_result():
    from schedflow.agent.runtime import AgentRuntime

    seen = []
    calls = [{"id": "call", "name": "read", "arguments": "{}"}]

    async def model(messages):
        seen.append(messages.copy())
        if len(seen) == 1:
            return {
                "calls": calls,
                "assistant": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "private reasoning",
                    "tool_calls": [],
                },
            }
        return {"calls": [], "assistant": {"role": "assistant", "content": "Done"}}

    async def tools(tool_calls):
        assert tool_calls == calls
        return [{"role": "tool", "tool_call_id": "call", "content": "result"}]

    runtime = AgentRuntime(model, tools, max_steps=2)
    assert {"model", "tools"} <= set(runtime.graph.get_graph().nodes)
    await runtime.run([{"role": "user", "content": "hello"}])
    assert seen[1][-2]["reasoning_content"] == "private reasoning"
    assert seen[1][-1]["content"] == "result"


@pytest.mark.asyncio
async def test_graph_steps_bound_model_and_tools_never_retry():
    from schedflow.agent.runtime import AgentRuntime

    effects = []

    async def model(messages):
        return {
            "calls": [{"id": "call", "name": "read", "arguments": "{}"}],
            "assistant": {"role": "assistant", "content": None},
        }

    async def tools(calls):
        effects.append(1)
        return [{"role": "tool", "tool_call_id": "call", "content": "result"}]

    runtime = AgentRuntime(model, tools, max_steps=1)
    with pytest.raises(ValueError, match="step limit"):
        await runtime.run([])
    assert effects == [1]

    async def broken(calls):
        effects.append(2)
        raise RuntimeError("tool failure")

    with pytest.raises(RuntimeError, match="tool failure"):
        await AgentRuntime(model, broken, max_steps=2).run([])
    assert effects == [1, 2]


@pytest.mark.asyncio
async def test_graph_cancellation_propagates_to_model_cleanup():
    from schedflow.agent.runtime import AgentRuntime

    entered, exited = asyncio.Event(), asyncio.Event()

    async def model(messages):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    async def tools(calls):
        raise AssertionError("Unexpected tool execution")

    task = asyncio.create_task(AgentRuntime(model, tools, max_steps=2).run([]))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited.is_set()


@pytest.mark.asyncio
async def test_service_output_limit_closes_stream_before_terminal_commit():
    from schedflow.agent import AgentConfig, AgentService
    from schedflow.core import Scheduler

    closed = []

    class Provider:
        async def stream(self, messages, tools):
            try:
                yield {"type": "text", "text": "x" * 600}
            finally:
                closed.append(True)

    svc = AgentService(
        Scheduler(),
        config=AgentConfig(enabled=True, model="local", max_tokens=64),
        provider=Provider(),
    )
    session = svc.repository.create_session("alice")["session_id"]
    turn = await svc.submit_turn("alice", session, "hello")
    await svc.wait_turn(turn["turn_id"])
    assert closed == [True]
    assert svc.repository.get("turn", "alice", turn["turn_id"])["status"] == "failed"
    await svc.close()


@pytest.mark.asyncio
async def test_model_node_closes_stream_on_output_limit_before_returning():
    from schedflow.agent import AgentConfig, AgentService
    from schedflow.core import Scheduler

    closed = []

    class Provider:
        async def stream(self, messages, tools):
            try:
                yield {"type": "text", "text": "x" * 600}
            finally:
                closed.append(True)

    svc = AgentService(
        Scheduler(),
        config=AgentConfig(enabled=True, model="local", max_tokens=64),
        provider=Provider(),
    )
    session = svc.repository.create_session("alice")["session_id"]
    with pytest.raises(ValueError, match="output exceeded"):
        await svc._model_step(
            "alice",
            {"session_id": session, "turn_id": "test"},
            {"message_id": "message", "blocks": []},
            [],
        )
    assert closed == [True]
    await svc.close()
