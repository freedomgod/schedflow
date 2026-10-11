"""LangGraph orchestration with bounded per-turn state and deterministic tools.

Business persistence and approval stay outside this graph. Opaque provider replay
data exists only in this turn's messages; no graph state is sent to the browser.
"""

import copy
import json
from typing import TypedDict


class TurnState(TypedDict):
    messages: list[dict]
    calls: list[dict]
    steps: int


class AgentRuntime:
    def __init__(self, model_step, tool_step, *, max_steps):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            raise ValueError(
                "Install schedflow[agent] to enable the LangGraph runtime"
            ) from None

        self.model_step, self.tool_step = model_step, tool_step
        self.max_steps = max_steps
        builder = StateGraph(TurnState)
        # No retry policy or checkpointer: tool effects must never replay implicitly.
        builder.add_node("model", self._model)
        builder.add_node("tools", self._tools)
        builder.add_edge(START, "model")
        builder.add_conditional_edges(
            "model", lambda state: "tools" if state["calls"] else END
        )
        builder.add_edge("tools", "model")
        self.graph = builder.compile()

    @staticmethod
    def _bounded(messages):
        if sum(len(json.dumps(m)) for m in messages) > 120000:
            raise ValueError("Assistant context exceeded the limit")

    async def _model(self, state):
        if state["steps"] >= self.max_steps:
            raise ValueError("Agent step limit reached; start another turn")
        self._bounded(state["messages"])
        result = await self.model_step(state["messages"])
        calls = result["calls"]
        if len(calls) > 16:
            raise ValueError("Too many tool calls")
        messages = state["messages"]
        if calls:
            messages = [*messages, copy.deepcopy(result["assistant"])]
            self._bounded(messages)
        return {"messages": messages, "calls": calls, "steps": state["steps"] + 1}

    async def _tools(self, state):
        results = await self.tool_step(state["calls"])
        messages = [*state["messages"], *results]
        self._bounded(messages)
        return {"messages": messages, "calls": []}

    async def run(self, messages):
        self._bounded(messages)
        return await self.graph.ainvoke(
            {"messages": copy.deepcopy(messages), "calls": [], "steps": 0},
            {"recursion_limit": 2 * self.max_steps + 2},
        )
