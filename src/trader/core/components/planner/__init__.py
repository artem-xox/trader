"""Planner — the "reason" step of the ReAct loop.

Calls the LLM (with tools bound) over the running conversation. The model decides whether
to request a tool call or to draft a final answer. The active skill (resolved from the
name in the state) selects which tools are available and what extra guidance is appended
to the base prompt; in normal mode only the base prompt and base tools are used.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from trader.core.models.schemas import AgentState, PlannerResponse
from trader.core.skills.base import SkillRegistry


class Planner:
    def __init__(
        self,
        model: BaseChatModel,
        registry: SkillRegistry,
        base_prompt: str,
        base_tools: list[BaseTool],
    ) -> None:
        self._model = model
        self._registry = registry
        self._base_prompt = base_prompt
        self._base_tools = base_tools

    async def __call__(self, state: AgentState) -> PlannerResponse:
        skill = self._registry.get(state.get("skill"))
        if skill is None:
            prompt, tools = self._base_prompt, self._base_tools
        else:
            prompt = f"{self._base_prompt}\n\n{skill.planner_prompt}"
            tools = list(skill.tools)

        model = self._model.bind_tools(tools) if tools else self._model
        response = await model.ainvoke([SystemMessage(prompt), *state["messages"]])
        return {"messages": [response], "iteration": state.get("iteration", 0) + 1}
