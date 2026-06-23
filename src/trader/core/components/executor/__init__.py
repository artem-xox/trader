"""Executor — the "act" step of the ReAct loop.

Runs the tool calls requested by the planner and returns their results as ToolMessages.
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from trader.core.models.schemas import AgentState, ExecutorResponse


class Executor:
    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools_by_name = {tool.name: tool for tool in tools}

    async def __call__(self, state: AgentState) -> ExecutorResponse:
        last = state["messages"][-1]
        results: list[ToolMessage] = []
        for call in last.tool_calls:
            tool = self._tools_by_name[call["name"]]
            output = await tool.ainvoke(call["args"])
            results.append(
                ToolMessage(
                    content=str(output),
                    name=call["name"],
                    tool_call_id=call["id"],
                )
            )
        return {"messages": results}
