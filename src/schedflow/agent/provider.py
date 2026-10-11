"""Streaming Chat Completions transport, imported without requiring httpx."""

import json


class ChatCompletionsProvider:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client
        self.owned = client is None

    async def close(self):
        if self.owned and self.client:
            await self.client.aclose()

    async def stream(self, messages, tools):
        if self.client is None:
            try:
                import httpx
            except ImportError as exc:
                raise ValueError(
                    "Install schedflow[agent] to use the model provider"
                ) from exc
            self.client = httpx.AsyncClient(timeout=self.config.timeout)
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            body["tools"] = tools
        calls = {}
        complete = False
        async with self.client.stream(
            "POST",
            self.config.base_url.rstrip("/") + "/chat/completions",
            json=body,
            headers=headers,
            timeout=self.config.timeout,
        ) as response:
            if response.status_code >= 400:
                raise ValueError(f"Model provider returned HTTP {response.status_code}")
            size = 0
            async for line in response.aiter_lines():
                size += len(line)
                if size > self.config.max_tokens * 32:
                    raise ValueError("Model response exceeded the configured limit")
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    complete = True
                    break
                packet = json.loads(raw)
                for choice in packet.get("choices", [])[:1]:
                    finish = choice.get("finish_reason")
                    if finish in {"length", "content_filter"}:
                        raise ValueError(
                            "Model response was truncated or filtered; no proposal accepted"
                        )
                    if finish in {"stop", "tool_calls"}:
                        complete = True
                    delta = choice.get("delta", {})
                    if delta.get("refusal"):
                        raise ValueError("Model declined the request")
                    if delta.get("content"):
                        yield {"type": "text", "text": delta["content"]}
                    for fragment in delta.get("tool_calls", []):
                        index = fragment["index"]
                        call = calls.setdefault(
                            index,
                            {
                                "type": "tool_call",
                                "id": "",
                                "name": "",
                                "arguments": "",
                            },
                        )
                        if fragment.get("id"):
                            call["id"] = fragment["id"]
                        function = fragment.get("function", {})
                        call["name"] += function.get("name", "")
                        call["arguments"] += function.get("arguments", "")
        if not complete:
            raise ValueError("Model stream ended before completion")
        for index in sorted(calls):
            json.loads(calls[index]["arguments"])
            yield calls[index]
