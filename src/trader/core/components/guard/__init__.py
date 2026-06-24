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

from trader.core.models.schemas import AgentState, GuardResponse, GuardVerdict


class Guard:
    
    async def __call__(self, _state: AgentState) -> GuardResponse:
        """Right now, just allow all tool calls."""
        return GuardResponse(guard_verdict=GuardVerdict.ALLOW, messages=[])
