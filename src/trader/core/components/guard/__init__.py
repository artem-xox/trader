"""Guard — safety gate that runs BEFORE tools are executed.

It judges the tool calls the planner proposed and decides whether they are safe to run.
This is the seam where dangerous actions are stopped (e.g. once trading tools exist:
oversized orders, withdrawals, anything irreversible). The active skill appends its own
policy to the base guard prompt.

The proposed calls are rendered as text rather than passed as a raw trailing message:
at guard time the planner's tool_calls are still unanswered, and feeding that history to
a structured-output call would be rejected by the model API.

Contract:
- `GuardVerdict.ALLOW` → the executor runs the tools.
- `GuardVerdict.BLOCK` → a feedback message is appended and control returns to the planner.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from trader.core.models.schemas import AgentState, GuardResponse, GuardVerdict
from trader.core.skills.base import SkillRegistry


class _GuardJudgment(BaseModel):
    verdict: GuardVerdict = Field(description="Whether the proposed tool calls may run.")
    reason: str = Field(description="One-line justification.")


def _render_tool_calls(tool_calls: list[dict]) -> str:
    return "\n".join(
        f"- {call['name']}({json.dumps(call.get('args', {}), ensure_ascii=False)})"
        for call in tool_calls
    )


class Guard:
    def __init__(self, model: BaseChatModel, registry: SkillRegistry, base_prompt: str) -> None:
        self._model = model.with_structured_output(_GuardJudgment)
        self._registry = registry
        self._base_prompt = base_prompt

    async def __call__(self, state: AgentState) -> GuardResponse:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []

        skill = self._registry.get(state.get("skill"))
        prompt = self._base_prompt if skill is None else f"{self._base_prompt}\n\n{skill.guard_prompt}"
        request = HumanMessage(f"Proposed tool calls:\n{_render_tool_calls(tool_calls)}")

        judgment: _GuardJudgment = await self._model.ainvoke([SystemMessage(prompt), request])
        if judgment.verdict == GuardVerdict.BLOCK:
            return {
                "guard_verdict": GuardVerdict.BLOCK,
                "messages": [
                    SystemMessage(f"A safety gate blocked your tool calls: {judgment.reason} Revise your plan.")
                ],
            }
        return {"guard_verdict": GuardVerdict.ALLOW}
