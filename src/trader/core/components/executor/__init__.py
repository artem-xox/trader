"""Executor — the "act" step of the ReAct loop.

Delegates to LangGraph's `ToolNode`: it runs the tool calls the planner requested in
parallel and returns their results as ToolMessages. Unlike a bare `asyncio.gather`,
`ToolNode` catches a tool that raises and turns it into a ToolMessage carrying the error,
so one failing tool feeds the planner a recoverable message instead of crashing the turn.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from trader.core.models.schemas import AgentState, ExecutorResponse


class Executor:
    def __init__(self, tools: list[BaseTool]) -> None:
        # handle_tool_errors defaults to True: a raising tool becomes an error ToolMessage.
        self._node = ToolNode(tools)

    async def __call__(self, state: AgentState) -> ExecutorResponse:
        return await self._node.ainvoke(state)
