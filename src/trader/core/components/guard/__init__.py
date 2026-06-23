"""Guard — safety gate that runs BEFORE tools are executed.

It inspects the tool calls the planner wants to make and decides whether they are safe
and adequate to run. This is the place to stop dangerous actions (e.g. once trading
tools exist: oversized orders, withdrawals, anything irreversible).

Contract:
- Input: the latest planner message carries the proposed `tool_calls`.
- Output: `{"guard_verdict": GuardVerdict}`.
  - `GuardVerdict.ALLOW` → the executor runs the tools.
  - `GuardVerdict.BLOCK` → control returns to the planner (which should revise its plan).

For now this is a stub that always allows. The `model` is held so a future version can
ask the LLM to judge whether the proposed tool calls are reasonable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from trader.core.models.schemas import AgentState, GuardResponse, GuardVerdict


class Guard:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def __call__(self, state: AgentState) -> GuardResponse:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        # TODO: use self._model to judge whether `tool_calls` are safe/adequate.
        _ = tool_calls
        return {"guard_verdict": GuardVerdict.ALLOW}
