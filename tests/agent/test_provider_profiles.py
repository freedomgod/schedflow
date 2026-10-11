"""Protocol contracts tested with HTTP streams, without model credentials."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from schedflow.agent import provider as module

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Lookup",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
        },
    }
]


def config(provider="custom", protocol="chat_completions", **overrides):
    values = {
        "provider": provider,
        "protocol": protocol,
        "base_url": "https://model.test/v1",
        "model": "test-model",
        "api_key": "secret-key",
        "max_tokens": 512,
        "timeout": 10,
        "workspace_id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def sse(*packets):
    return "".join(
        "data: " + (packet if isinstance(packet, str) else json.dumps(packet)) + "\n\n"
        for packet in packets
    )


def factory(cfg, client):
    create = getattr(module, "create_provider", None)
    assert callable(create), "provider factory must be available"
    return create(cfg, client=client)


async def collect(cfg, packets, messages=None, status=200):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text=sse(*packets))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = factory(cfg, client)
        events = [event async for event in adapter.stream(messages or [], TOOLS)]
    return events, requests


def test_catalogue_is_json_and_covers_verified_profiles():
    catalogue = getattr(module, "provider_catalog", None)
    assert callable(catalogue), "provider catalogue must be exported"
    rows = catalogue()
    assert [row["id"] for row in rows] == [
        "openai",
        "deepseek",
        "qwen",
        "kimi",
        "glm",
        "claude",
        "gemini",
        "custom",
    ]
    assert json.loads(json.dumps(rows)) == rows
    by_id = {row["id"]: row for row in rows}
    assert by_id["openai"]["protocol"] == "responses"
    assert by_id["claude"]["protocol"] == "anthropic_messages"
    assert by_id["kimi"]["models"] == ["kimi-k2.6"]
    assert {row["id"] for row in by_id["qwen"]["regions"]} == {
        "cn-beijing",
        "ap-southeast-1",
        "us-east-1",
    }
    assert "{WorkspaceId}" in by_id["qwen"]["base_url"]
    rows[0]["models"].clear()
    assert catalogue()[0]["models"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile,token_key,extra",
    [
        ("custom", "max_tokens", {}),
        ("deepseek", "max_tokens", {"thinking": {"type": "disabled"}}),
        ("qwen", "max_tokens", {}),
        ("kimi", "max_tokens", {}),
        ("openai", "max_completion_tokens", {}),
        ("glm", "max_tokens", {"tool_stream": True}),
        ("gemini", "max_tokens", {}),
    ],
)
async def test_chat_profiles_replay_fragmented_reasoning_and_signature(
    profile, token_key, extra
):
    packets = [
        {"choices": [{"delta": {"reasoning_content": "Think "}}]},
        {
            "choices": [
                {
                    "delta": {
                        "content": "Hello",
                        "reasoning_content": "more",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call1",
                                "type": "function",
                                "function": {"name": "look", "arguments": '{"id":'},
                                "extra_content": {
                                    "google": {"thought_signature": "opaque"}
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
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"name": "up", "arguments": '"a"}'},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {"choices": [], "usage": {"total_tokens": 5}},
        "[DONE]",
    ]
    cfg = config(profile)
    events, requests = await collect(cfg, packets)
    assert events[0] == {"type": "text", "text": "Hello"}
    assert events[-2] == {
        "type": "tool_call",
        "id": "call1",
        "name": "lookup",
        "arguments": '{"id":"a"}',
    }
    message = events[-1]["message"]
    assert events[-1]["type"] == "assistant_message"
    assert message["content"] == "Hello"
    assert message["reasoning_content"] == "Think more"
    assert (
        message["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
        == "opaque"
    )
    body = json.loads(requests[0].content)
    assert body[token_key] == 512
    for key, value in extra.items():
        assert body[key] == value
    if token_key != "max_tokens":
        assert "max_tokens" not in body
    _, follow = await collect(
        cfg,
        [{"choices": [{"delta": {"content": "Done"}, "finish_reason": "stop"}]}],
        [message, {"role": "tool", "tool_call_id": "call1", "content": "result"}],
    )
    assert json.loads(follow[0].content)["messages"][0] == message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail",
    [
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
        {"choices": [{"delta": {"refusal": "private details"}}]},
        {"error": {"message": "secret-key private details"}},
        "{bad-secret-key-json",
        None,
    ],
)
async def test_chat_rejects_incomplete_or_bad_stream_before_tool_events(tail):
    packets = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call1",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        }
    ]
    if tail is not None:
        packets.append(tail)
    events = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=sse(*packets))
        )
    ) as client:
        with pytest.raises(ValueError) as exc:
            async for event in factory(config(), client).stream([], TOOLS):
                events.append(event)
    assert not any(event["type"] == "tool_call" for event in events)
    assert "secret-key" not in str(exc.value)
    assert "private details" not in str(exc.value)


@pytest.mark.asyncio
async def test_all_tool_arguments_validate_before_any_tool_is_emitted():
    packets = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "a",
                                "function": {"name": "lookup", "arguments": "{}"},
                            },
                            {
                                "index": 1,
                                "id": "b",
                                "function": {"name": "lookup", "arguments": "{bad"},
                            },
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    ]
    events = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=sse(*packets))
        )
    ) as client:
        with pytest.raises(ValueError):
            async for event in factory(config(), client).stream([], TOOLS):
                events.append(event)
    assert events == []


@pytest.mark.asyncio
async def test_chat_done_without_finish_reason_never_releases_tools():
    packets = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call1",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        },
        "[DONE]",
    ]
    events = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=sse(*packets))
        )
    ) as client:
        with pytest.raises(ValueError, match="before completion"):
            async for event in factory(config(), client).stream([], TOOLS):
                events.append(event)
    assert events == []


@pytest.mark.asyncio
async def test_responses_replay_output_reasoning_and_native_function_result():
    output = [
        {
            "type": "reasoning",
            "id": "rs1",
            "summary": [],
            "encrypted_content": "encrypted",
        },
        {
            "type": "message",
            "id": "msg1",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hi"}],
        },
        {
            "type": "function_call",
            "id": "fc1",
            "call_id": "call1",
            "name": "lookup",
            "arguments": '{"id":"a"}',
            "status": "completed",
        },
    ]
    packets = [
        {"type": "response.output_text.delta", "delta": "Hi"},
        {
            "type": "response.output_item.added",
            "output_index": 2,
            "item": {**output[2], "arguments": ""},
        },
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 2,
            "delta": '{"id":',
        },
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 2,
            "delta": '"a"}',
        },
        {
            "type": "response.completed",
            "response": {"status": "completed", "output": output},
        },
    ]
    cfg = config("openai", "responses")
    events, requests = await collect(
        cfg,
        packets,
        [{"role": "system", "content": "Rules"}, {"role": "user", "content": "Go"}],
    )
    assert str(requests[0].url).endswith("/responses")
    body = json.loads(requests[0].content)
    assert body["store"] is False
    assert body["max_output_tokens"] == 512
    assert "reasoning.encrypted_content" in body["include"]
    assert body["tools"][0]["name"] == "lookup"
    assert body["tools"][0]["strict"] is False
    assert events[-2]["id"] == "call1"
    message = events[-1]["message"]
    assert message["_provider"]["output"] == output
    _, follow = await collect(
        cfg,
        [
            {
                "type": "response.completed",
                "response": {"status": "completed", "output": []},
            }
        ],
        [message, {"role": "tool", "tool_call_id": "call1", "content": "value"}],
    )
    assert json.loads(follow[0].content)["input"] == [
        *output,
        {"type": "function_call_output", "call_id": "call1", "output": "value"},
    ]


@pytest.mark.asyncio
async def test_anthropic_replay_thinking_signature_tool_blocks_and_workspace():
    packets = [
        {
            "type": "message_start",
            "message": {"id": "msg", "role": "assistant", "content": []},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "plan"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "signed"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Hi"},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "content_block_start",
            "index": 2,
            "content_block": {
                "type": "tool_use",
                "id": "call1",
                "name": "lookup",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 2,
            "delta": {"type": "input_json_delta", "partial_json": '{"id":'},
        },
        {
            "type": "content_block_delta",
            "index": 2,
            "delta": {"type": "input_json_delta", "partial_json": '"a"}'},
        },
        {"type": "content_block_stop", "index": 2},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
        {"type": "message_stop"},
    ]
    cfg = config("claude", "anthropic_messages", workspace_id="workspace")
    events, requests = await collect(
        cfg,
        packets,
        [{"role": "system", "content": "Rules"}, {"role": "user", "content": "Go"}],
    )
    assert str(requests[0].url).endswith("/messages")
    assert requests[0].headers["anthropic-version"] == "2023-06-01"
    assert requests[0].headers["anthropic-workspace-id"] == "workspace"
    body = json.loads(requests[0].content)
    assert body["system"] == "Rules"
    assert body["tools"][0]["input_schema"] == TOOLS[0]["function"]["parameters"]
    assert events[-2]["arguments"] == '{"id":"a"}'
    message = events[-1]["message"]
    blocks = message["_provider"]["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "plan", "signature": "signed"}
    _, follow = await collect(
        cfg,
        [
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"},
        ],
        [message, {"role": "tool", "tool_call_id": "call1", "content": "value"}],
    )
    assert json.loads(follow[0].content)["messages"] == [
        {"role": "assistant", "content": blocks},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call1", "content": "value"}
            ],
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol", ["chat_completions", "responses", "anthropic_messages"]
)
@pytest.mark.parametrize("status", [302, 401, 500])
async def test_http_errors_are_sanitized_without_redirect_or_retry(protocol, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="secret-key private details",
            headers={"location": "https://other.test"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(ValueError) as exc:
            _ = [
                e
                async for e in factory(config(protocol=protocol), client).stream(
                    [], TOOLS
                )
            ]
    assert len(requests) == 1
    assert "secret-key" not in str(exc.value)
    assert str(status) in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol,packets",
    [
        (
            "responses",
            [{"type": "response.incomplete", "response": {"status": "incomplete"}}],
        ),
        ("responses", [{"type": "response.output_text.delta", "delta": "partial"}]),
        (
            "responses",
            [
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "one",
                                "name": "lookup",
                                "arguments": "{}",
                            },
                            {
                                "type": "message",
                                "content": [
                                    {"type": "refusal", "refusal": "private refusal"}
                                ],
                            },
                        ],
                    },
                }
            ],
        ),
        (
            "anthropic_messages",
            [
                {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}},
                {"type": "message_stop"},
            ],
        ),
        (
            "anthropic_messages",
            [{"type": "message_delta", "delta": {"stop_reason": "tool_use"}}],
        ),
        (
            "anthropic_messages",
            [
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "one",
                        "name": "lookup",
                        "input": {},
                    },
                },
                {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
                {"type": "message_stop"},
            ],
        ),
    ],
)
async def test_native_protocols_reject_incomplete_refusal_and_unclosed_blocks(
    protocol, packets
):
    events = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=sse(*packets))
        )
    ) as client:
        with pytest.raises(ValueError) as exc:
            async for event in factory(config(protocol=protocol), client).stream(
                [], TOOLS
            ):
                events.append(event)
    assert not any(event["type"] == "tool_call" for event in events)
    assert "private refusal" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol", ["chat_completions", "responses", "anthropic_messages"]
)
async def test_stream_size_is_bounded_even_without_sse_line_end(protocol):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"data: " + b"x" * 65537)
        )
    ) as client:
        with pytest.raises(ValueError, match="configured limit"):
            _ = [
                e
                async for e in factory(config(protocol=protocol), client).stream(
                    [], TOOLS
                )
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol", ["chat_completions", "responses", "anthropic_messages"]
)
async def test_closing_consumer_immediately_closes_http_stream(protocol):
    first = {
        "chat_completions": sse({"choices": [{"delta": {"content": "Hello"}}]}),
        "responses": sse({"type": "response.output_text.delta", "delta": "Hello"}),
        "anthropic_messages": sse(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hello"},
            },
        ),
    }[protocol]

    class ChunkStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield first.encode()
            yield b"data: [DONE]\n\n"

        async def aclose(self):
            self.closed = True

    incoming = ChunkStream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=incoming)
        )
    ) as client:
        adapter = factory(config(protocol=protocol), client)
        stream = adapter.stream([], TOOLS)
        assert await anext(stream) == {"type": "text", "text": "Hello"}
        await stream.aclose()
        assert incoming.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol", ["chat_completions", "responses", "anthropic_messages"]
)
async def test_cancel_during_network_read_closes_response_without_retry(protocol):
    waiting = asyncio.Event()
    requests = []

    class WaitingStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            waiting.set()
            await asyncio.Event().wait()
            yield b""

        async def aclose(self):
            self.closed = True

    incoming = WaitingStream()

    def handler(request):
        requests.append(request)
        return httpx.Response(200, stream=incoming)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = factory(config(protocol=protocol), client)

        async def read():
            return [event async for event in adapter.stream([], TOOLS)]

        task = asyncio.create_task(read())
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert incoming.closed
        assert len(requests) == 1
        await adapter.close()
        assert not client.is_closed


def chat_tool_delta():
    return {
        "tool_calls": [
            {
                "index": 0,
                "id": "call1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }
        ]
    }


def claude_tool_blocks():
    return [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "call1",
                "name": "lookup",
                "input": {},
            },
        },
        {"type": "content_block_stop", "index": 0},
    ]


def responses_completed():
    return {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call1",
                    "name": "lookup",
                    "arguments": "{}",
                },
            ],
        },
    }


async def assert_rejected_without_tools(protocol, packets):
    events = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=sse(*packets))
        )
    ) as client:
        with pytest.raises(ValueError):
            async for event in factory(config(protocol=protocol), client).stream(
                [], TOOLS
            ):
                events.append(event)
    assert not any(
        event["type"] in {"tool_call", "assistant_message"} for event in events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_calls,reason", [(True, "stop"), (False, "tool_calls")])
async def test_chat_completion_reason_must_match_tool_presence(has_calls, reason):
    await assert_rejected_without_tools(
        "chat_completions",
        [
            {
                "choices": [
                    {
                        "delta": chat_tool_delta() if has_calls else {},
                        "finish_reason": reason,
                    }
                ]
            },
            "[DONE]",
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail",
    [
        {"choices": [{"delta": {"content": "late"}}]},
        {"choices": [{"delta": {"reasoning_content": "late"}}]},
        {
            "choices": [
                {"delta": {"extra_content": {"google": {"thought_signature": "late"}}}}
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "two",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        "after_done",
    ],
)
async def test_chat_semantic_data_after_completion_rejects_entire_tool_batch(tail):
    packets = [
        {"choices": [{"delta": chat_tool_delta(), "finish_reason": "tool_calls"}]}
    ]
    if tail == "after_done":
        packets.extend(["[DONE]", {"choices": [{"delta": {"content": "late"}}]}])
    else:
        packets.extend([tail, "[DONE]"])
    await assert_rejected_without_tools("chat_completions", packets)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "has_calls,reason",
    [
        (True, "end_turn"),
        (True, "stop_sequence"),
        (False, "tool_use"),
    ],
)
async def test_claude_completion_reason_must_match_tool_presence(has_calls, reason):
    await assert_rejected_without_tools(
        "anthropic_messages",
        [
            *(claude_tool_blocks() if has_calls else []),
            {"type": "message_delta", "delta": {"stop_reason": reason}},
            {"type": "message_stop"},
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail",
    [
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "text", "text": "late"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": " "},
        },
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
        {"type": "message_start", "message": {"content": []}},
        {"type": "message_stop"},
        "late_block_before_message_stop",
    ],
)
async def test_claude_semantic_data_after_completion_rejects_entire_tool_batch(tail):
    packets = [
        *claude_tool_blocks(),
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
    ]
    if tail == "late_block_before_message_stop":
        packets.extend(
            [
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {
                        "type": "tool_use",
                        "id": "two",
                        "name": "lookup",
                        "input": {},
                    },
                },
                {"type": "content_block_stop", "index": 1},
                {"type": "message_stop"},
            ]
        )
    else:
        packets.extend([{"type": "message_stop"}, tail])
    await assert_rejected_without_tools("anthropic_messages", packets)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail",
    [
        {"type": "response.output_text.delta", "delta": "late"},
        {
            "type": "response.function_call_arguments.delta",
            "output_index": 0,
            "delta": " ",
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {"type": "function_call"},
        },
        {
            "type": "response.completed",
            "response": {"status": "completed", "output": []},
        },
        "after_done",
    ],
)
async def test_responses_semantic_data_after_completion_rejects_entire_tool_batch(tail):
    packets = [responses_completed()]
    if tail == "after_done":
        packets.extend(
            ["[DONE]", {"type": "response.output_text.delta", "delta": "late"}]
        )
    else:
        packets.append(tail)
    await assert_rejected_without_tools("responses", packets)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol,packets",
    [
        (
            "chat_completions",
            [
                {
                    "choices": [
                        {"delta": chat_tool_delta(), "finish_reason": "tool_calls"}
                    ]
                },
                {"choices": [], "usage": {"total_tokens": 3}},
                {
                    "choices": [{"delta": {}, "finish_reason": None}],
                    "usage": {"total_tokens": 3},
                },
                {"type": "ping"},
                "[DONE]",
            ],
        ),
        (
            "anthropic_messages",
            [
                *claude_tool_blocks(),
                {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
                {"type": "message_delta", "delta": {}, "usage": {"output_tokens": 3}},
                {"type": "message_stop"},
                {"type": "ping"},
                {"type": "message_delta", "delta": {}, "usage": {"output_tokens": 3}},
            ],
        ),
        ("responses", [responses_completed(), {"type": "ping"}]),
    ],
)
async def test_nonsemantic_usage_and_ping_trailers_preserve_valid_tool_completion(
    protocol, packets
):
    events, _ = await collect(config(protocol=protocol), packets)
    assert [e["id"] for e in events if e["type"] == "tool_call"] == ["call1"]
    assert events[-1]["type"] == "assistant_message"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,model",
    [
        ("deepseek", "deepseek-flash"),
        ("kimi", "kimi-k2.6"),
    ],
)
async def test_disabled_thinking_profiles_accept_history_without_reasoning_across_user_turns(
    provider, model
):
    history = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": "New question"},
    ]
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        if body.get("thinking") != {"type": "disabled"}:
            return httpx.Response(
                400, text="Thinking tools require missing historical reasoning"
            )
        if len(requests) == 1:
            packets = [
                {
                    "choices": [
                        {"delta": chat_tool_delta(), "finish_reason": "tool_calls"}
                    ]
                },
                "[DONE]",
            ]
        else:
            packets = [
                {
                    "choices": [
                        {"delta": {"content": "Answer"}, "finish_reason": "stop"}
                    ]
                },
                "[DONE]",
            ]
        return httpx.Response(200, text=sse(*packets))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = factory(config(provider, model=model), client)
        first = [e async for e in adapter.stream(history, TOOLS)]
        history.extend(
            [
                first[-1]["message"],
                {"role": "tool", "tool_call_id": "call1", "content": "value"},
            ]
        )
        second = [e async for e in adapter.stream(history, TOOLS)]
    assert second[-1]["message"]["content"] == "Answer"
    assert len(requests) == 2
    assert all(
        json.loads(req.content)["thinking"] == {"type": "disabled"} for req in requests
    )
    assert json.loads(requests[1].content)["messages"] == history


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model", ["kimi-k3", "kimi-k2.7-code", "kimi-k2.7-code-highspeed", "test-model"]
)
async def test_kimi_thinking_disabled_is_specific_to_k26(model):
    _, requests = await collect(
        config("kimi", model=model),
        [
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ],
    )
    assert "thinking" not in json.loads(requests[0].content)


@pytest.mark.asyncio
async def test_kimi_k26_uses_its_documented_max_tokens_field():
    _, requests = await collect(
        config("kimi", model="kimi-k2.6"),
        [
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ],
    )
    body = json.loads(requests[0].content)
    assert body.get("max_tokens") == 512
    assert "max_completion_tokens" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["custom", "qwen", "kimi", "glm", "gemini"])
async def test_other_chat_profiles_do_not_force_deepseek_thinking_control(profile):
    _, requests = await collect(
        config(profile), [{"choices": [{"delta": {}, "finish_reason": "stop"}]}]
    )
    assert "thinking" not in json.loads(requests[0].content)
