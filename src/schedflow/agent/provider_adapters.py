"""Bounded SSE protocols with lossless, server-only assistant replay.

Only text streams immediately. Tools are released after successful completion
and validation of every argument object. ``_provider`` must stay server-side.
"""

import json
from contextlib import aclosing
from copy import deepcopy


def _invalid_constant(value):
    raise ValueError("Invalid JSON constant")


def _json(raw):
    try:
        return json.loads(raw, parse_constant=_invalid_constant)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Model provider returned invalid JSON") from None


def _calls_events(calls):
    events, seen = [], set()
    for call in calls:
        function = call["function"]
        call_id, name, arguments = call["id"], function["name"], function["arguments"]
        if not isinstance(call_id, str) or not call_id or call_id in seen:
            raise ValueError("Model provider returned an invalid tool call")
        seen.add(call_id)
        if not isinstance(name, str) or not name or not isinstance(arguments, str):
            raise ValueError("Model provider returned an invalid tool call")
        if not isinstance(_json(arguments), dict):
            raise TypeError("Model tool arguments must be a JSON object")
        events.append(
            {"type": "tool_call", "id": call_id, "name": name, "arguments": arguments}
        )
    return events


def _merge(target, extra):
    """Retain vendor fields without interpreting opaque thought signatures."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


class _StreamingProvider:
    endpoint = ""

    def __init__(self, config, client=None):
        self.config, self.client = config, client
        self.owned = client is None

    async def close(self):
        if self.owned and self.client:
            await self.client.aclose()

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        return headers

    async def stream(self, messages, tools):
        try:
            async with aclosing(self._events(messages, tools)) as events:
                async for event in events:
                    yield event
        except (KeyError, TypeError, IndexError, AttributeError, RecursionError):
            raise ValueError("Model provider returned a malformed response") from None

    async def _packets(self, body):
        try:
            import httpx
        except ImportError as exc:
            raise ValueError(
                "Install schedflow[agent] to use the model provider"
            ) from exc
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=self.config.timeout, follow_redirects=False
            )
        try:
            async with self.client.stream(
                "POST",
                self.config.base_url.rstrip("/") + self.endpoint,
                json=body,
                headers=self._headers(),
                timeout=self.config.timeout,
                follow_redirects=False,
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise ValueError(
                        f"Model provider returned HTTP {response.status_code}"
                    )
                size, buffer, data = 0, b"", []
                limit = min(8 * 1024 * 1024, max(16384, self.config.max_tokens * 128))
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Model response exceeded the configured limit")
                    buffer += chunk
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        line = raw_line.rstrip(b"\r").decode("utf-8")
                        if not line:
                            if data:
                                yield self._packet("\n".join(data))
                                data.clear()
                        elif line.startswith("data:"):
                            data.append(line[5:].lstrip(" "))
                if buffer:
                    line = buffer.rstrip(b"\r").decode("utf-8")
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip(" "))
                if data:
                    yield self._packet("\n".join(data))
        except httpx.HTTPError:
            raise ValueError("Model provider connection failed") from None
        except UnicodeError:
            raise ValueError(
                "Model provider returned invalid stream encoding"
            ) from None

    @staticmethod
    def _packet(raw):
        if raw.strip() == "[DONE]":
            return None
        packet = _json(raw)
        if not isinstance(packet, dict):
            raise TypeError("Model provider returned a malformed response")
        if packet.get("error") or packet.get("type") == "error":
            raise ValueError("Model provider reported a stream error")
        return packet


class ChatCompletionsProvider(_StreamingProvider):
    endpoint = "/chat/completions"

    async def _events(self, messages, tools):
        profile = getattr(self.config, "provider", "custom")
        body = {
            "model": self.config.model,
            "messages": [
                {k: deepcopy(v) for k, v in message.items() if k != "_provider"}
                for message in messages
            ],
            "stream": True,
            "max_completion_tokens"
            if profile == "openai"
            else "max_tokens": self.config.max_tokens,
        }
        if tools:
            body["tools"] = tools
            if profile == "glm":
                body["tool_stream"] = True
        if profile == "deepseek":
            # Persisted user-turn history does not retain reasoning_content.
            # DeepSeek thinking + tools requires replay across every prior turn.
            body["thinking"] = {"type": "disabled"}
        elif profile == "kimi" and self.config.model == "kimi-k2.6":
            # K2.6 supports non-thinking tool use without preserved history.
            body["thinking"] = {"type": "disabled"}
        assistant = {"role": "assistant", "content": ""}
        calls, reason, done = {}, None, False
        async with aclosing(self._packets(body)) as packets:
            async for packet in packets:
                if packet is None:
                    done = True
                    continue
                for choice in packet.get("choices", [])[:1]:
                    finish = choice.get("finish_reason")
                    delta = choice.get("delta", {})
                    if (reason is not None or done) and any(delta.values()):
                        raise ValueError(
                            "Model provider returned content after completion"
                        )
                    if finish is not None and (
                        done or (reason is not None and finish != reason)
                    ):
                        raise ValueError(
                            "Model provider returned conflicting completion reasons"
                        )
                    if finish in {"length", "content_filter"}:
                        raise ValueError(
                            "Model response was truncated or filtered; no proposal accepted"
                        )
                    if finish in {"stop", "tool_calls"}:
                        reason = finish
                    elif finish is not None:
                        raise ValueError(
                            "Model provider returned an unsupported completion reason"
                        )
                    if delta.get("refusal"):
                        raise ValueError("Model declined the request")
                    if delta.get("content"):
                        if not isinstance(delta["content"], str):
                            raise ValueError("Model provider returned invalid text")
                        assistant["content"] += delta["content"]
                        yield {"type": "text", "text": delta["content"]}
                    if delta.get("reasoning_content"):
                        assistant["reasoning_content"] = (
                            assistant.get("reasoning_content", "")
                            + delta["reasoning_content"]
                        )
                    _merge(
                        assistant,
                        {
                            k: v
                            for k, v in delta.items()
                            if k
                            not in {
                                "content",
                                "role",
                                "tool_calls",
                                "reasoning_content",
                                "refusal",
                            }
                        },
                    )
                    for fragment in delta.get("tool_calls", []):
                        index = fragment["index"]
                        if (
                            not isinstance(index, int)
                            or isinstance(index, bool)
                            or index < 0
                        ):
                            raise ValueError(
                                "Model provider returned an invalid tool index"
                            )
                        call = calls.setdefault(
                            index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if fragment.get("id"):
                            call["id"] = fragment["id"]
                        function = fragment.get("function", {})
                        call["function"]["name"] += function.get("name", "")
                        call["function"]["arguments"] += function.get("arguments", "")
                        _merge(
                            call,
                            {
                                k: v
                                for k, v in fragment.items()
                                if k not in {"index", "id", "function"}
                            },
                        )
                        _merge(
                            call["function"],
                            {
                                k: v
                                for k, v in function.items()
                                if k not in {"name", "arguments"}
                            },
                        )
        if reason is None:
            raise ValueError("Model stream ended before completion")
        ordered = [calls[index] for index in sorted(calls)]
        if reason != ("tool_calls" if ordered else "stop"):
            raise ValueError("Model completion reason did not match tool calls")
        events = _calls_events(ordered)
        if ordered:
            assistant["tool_calls"] = ordered
        for event in events:
            yield event
        yield {"type": "assistant_message", "message": assistant}


class OpenAIResponsesProvider(_StreamingProvider):
    endpoint = "/responses"

    @staticmethod
    def _input(messages):
        items = []
        for message in messages:
            replay = message.get("_provider", {})
            if message["role"] == "assistant" and replay.get("protocol") == "responses":
                items.extend(deepcopy(replay["output"]))
            elif message["role"] == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["tool_call_id"],
                        "output": message["content"],
                    }
                )
            else:
                if message.get("content"):
                    items.append(
                        {"role": message["role"], "content": message["content"]}
                    )
                for call in message.get("tool_calls", []):
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call["id"],
                            "name": call["function"]["name"],
                            "arguments": call["function"]["arguments"],
                        }
                    )
        return items

    async def _events(self, messages, tools):
        body = {
            "model": self.config.model,
            "input": self._input(messages),
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": self.config.max_tokens,
        }
        if tools:
            body["tools"] = [
                {"type": "function", "strict": False, **deepcopy(tool["function"])}
                for tool in tools
            ]
        response, done = None, False
        async with aclosing(self._packets(body)) as packets:
            async for packet in packets:
                if packet is None:
                    done = True
                    continue
                kind = packet.get("type", "")
                if kind == "ping":
                    continue
                if response is not None or done:
                    raise ValueError(
                        "Model provider returned an event after completion"
                    )
                if kind in {"response.failed", "response.incomplete", "response.error"}:
                    raise ValueError("Model response failed or was incomplete")
                if kind.startswith("response.refusal."):
                    raise ValueError("Model declined the request")
                if kind == "response.output_text.delta":
                    if not isinstance(packet["delta"], str):
                        raise ValueError("Model provider returned invalid text")
                    yield {"type": "text", "text": packet["delta"]}
                if kind == "response.completed":
                    response = packet["response"]
                    if (
                        response.get("status") != "completed"
                        or response.get("error")
                        or response.get("incomplete_details")
                    ):
                        raise ValueError("Model response failed or was incomplete")
                    # Trailing stream errors must still reject tools.
        if response is None:
            raise ValueError("Model stream ended before completion")
        output, calls, text = response["output"], [], ""
        if not isinstance(output, list):
            raise TypeError("Model provider returned a malformed response")
        for item in output:
            if item.get("status") in {"incomplete", "failed", "in_progress"}:
                raise ValueError("Model response failed or was incomplete")
            if item.get("type") == "function_call":
                calls.append(
                    {
                        "id": item["call_id"],
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "arguments": item["arguments"],
                        },
                    }
                )
            elif item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "refusal":
                        raise ValueError("Model declined the request")
                    if block.get("type") == "output_text":
                        text += block["text"]
        events = _calls_events(calls)
        assistant = {
            "role": "assistant",
            "content": text,
            "_provider": {"protocol": "responses", "output": deepcopy(output)},
        }
        if calls:
            assistant["tool_calls"] = calls
        for event in events:
            yield event
        yield {"type": "assistant_message", "message": assistant}


class AnthropicMessagesProvider(_StreamingProvider):
    endpoint = "/messages"

    def _headers(self):
        headers = super()._headers()
        headers["anthropic-version"] = "2023-06-01"
        if getattr(self.config, "workspace_id", ""):
            headers["anthropic-workspace-id"] = self.config.workspace_id
        return headers

    @staticmethod
    def _messages(messages):
        result, systems = [], []
        for message in messages:
            role, replay = message["role"], message.get("_provider", {})
            if role == "system":
                systems.append(message["content"])
                continue
            if role == "tool":
                role = "user"
                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                ]
            elif role == "assistant" and replay.get("protocol") == "anthropic_messages":
                blocks = deepcopy(replay["content"])
            else:
                blocks = (
                    [{"type": "text", "text": message["content"]}]
                    if message.get("content")
                    else []
                )
                for call in message.get("tool_calls", []):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "input": _json(call["function"]["arguments"]),
                        }
                    )
            if result and result[-1]["role"] == role:
                result[-1]["content"].extend(blocks)
            else:
                result.append({"role": role, "content": blocks})
        return result, "\n\n".join(systems)

    async def _events(self, messages, tools):
        converted, system = self._messages(messages)
        body = {
            "model": self.config.model,
            "messages": converted,
            "stream": True,
            "max_tokens": self.config.max_tokens,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": tool["function"]["name"],
                    "description": tool["function"].get("description", ""),
                    "input_schema": deepcopy(tool["function"]["parameters"]),
                }
                for tool in tools
            ]
        blocks, inputs, stopped = {}, {}, set()
        complete, reason, done = False, None, False
        async with aclosing(self._packets(body)) as packets:
            async for packet in packets:
                if packet is None:
                    done = True
                    continue
                kind = packet.get("type")
                if kind == "ping":
                    continue
                if (
                    (reason is not None or complete or done)
                    and kind != "message_delta"
                    and (kind != "message_stop" or complete or done)
                ):
                    raise ValueError(
                        "Model provider returned an event after completion"
                    )
                if kind == "content_block_start":
                    index = packet["index"]
                    if index in blocks:
                        raise ValueError(
                            "Model provider returned a duplicate content block"
                        )
                    blocks[index] = deepcopy(packet["content_block"])
                elif kind == "content_block_delta":
                    index, delta = packet["index"], packet["delta"]
                    if index in stopped:
                        raise ValueError(
                            "Model provider returned content after block completion"
                        )
                    block = blocks[index]
                    delta_kind = delta["type"]
                    if delta_kind == "text_delta":
                        block["text"] += delta["text"]
                        yield {"type": "text", "text": delta["text"]}
                    elif delta_kind == "thinking_delta":
                        block["thinking"] += delta["thinking"]
                    elif delta_kind == "signature_delta":
                        block["signature"] = (
                            block.get("signature", "") + delta["signature"]
                        )
                    elif delta_kind == "input_json_delta":
                        inputs[index] = inputs.get(index, "") + delta["partial_json"]
                    else:
                        raise ValueError(
                            "Model provider returned an unsupported content delta"
                        )
                elif kind == "content_block_stop":
                    if packet["index"] not in blocks or packet["index"] in stopped:
                        raise ValueError(
                            "Model provider returned an invalid block completion"
                        )
                    stopped.add(packet["index"])
                elif kind == "message_delta":
                    delta = packet["delta"]
                    new_reason = delta.get("stop_reason")
                    if (reason is not None or complete or done) and any(
                        value for key, value in delta.items() if key != "stop_reason"
                    ):
                        raise ValueError(
                            "Model provider returned content after completion"
                        )
                    if new_reason is not None:
                        if (
                            complete
                            or done
                            or (reason is not None and new_reason != reason)
                        ):
                            raise ValueError(
                                "Model provider returned conflicting completion reasons"
                            )
                        reason = new_reason
                    if reason in {"max_tokens", "refusal", "pause_turn"}:
                        raise ValueError("Model response was incomplete or declined")
                elif kind == "message_stop":
                    if reason is None:
                        raise ValueError("Model stream ended before completion")
                    complete = True
        if (
            not complete
            or reason not in {"end_turn", "tool_use", "stop_sequence"}
            or set(blocks) != stopped
        ):
            raise ValueError("Model stream ended before completion")
        ordered, calls, text = [blocks[index] for index in sorted(blocks)], [], ""
        for index in sorted(blocks):
            block = blocks[index]
            if block["type"] == "tool_use":
                if index in inputs:
                    block["input"] = _json(inputs[index])
                arguments = (
                    inputs[index]
                    if index in inputs
                    else json.dumps(block["input"], separators=(",", ":"))
                )
                calls.append(
                    {
                        "id": block["id"],
                        "type": "function",
                        "function": {"name": block["name"], "arguments": arguments},
                    }
                )
            elif block["type"] == "text":
                text += block["text"]
        if (calls and reason != "tool_use") or (
            not calls and reason not in {"end_turn", "stop_sequence"}
        ):
            raise ValueError("Model completion reason did not match tool calls")
        events = _calls_events(calls)
        assistant = {
            "role": "assistant",
            "content": text,
            "_provider": {"protocol": "anthropic_messages", "content": ordered},
        }
        if calls:
            assistant["tool_calls"] = calls
        for event in events:
            yield event
        yield {"type": "assistant_message", "message": assistant}
