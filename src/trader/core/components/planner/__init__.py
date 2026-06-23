"""Planner — the "reason" step of the ReAct loop.

Calls the LLM (with tools bound) over the running conversation. The model decides whether
to request a tool call or to draft a final answer. Kept deliberately simple for now; will
grow into explicit step planning later.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from trader.core.models.schemas import AgentState, PlannerResponse


class Planner:
    def __init__(self, model: BaseChatModel, tools: list[BaseTool], prompt: str) -> None:
        self._model = model.bind_tools(tools)
        self._prompt = prompt

    async def __call__(self, state: AgentState) -> PlannerResponse:
        messages = [SystemMessage(self._prompt), *state["messages"]]
        response = await self._model.ainvoke(messages)
        return {"messages": [response], "iteration": state.get("iteration", 0) + 1}
