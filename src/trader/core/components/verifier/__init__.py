"""Verifier — final gate that checks the planner's drafted answer before it leaves.

Contract:
- Input: the latest planner message is a final answer (no tool calls).
- Output: `{"review_verdict": ReviewVerdict}`.
  - `ReviewVerdict.OK` → the answer is returned to the caller.
  - `ReviewVerdict.REVISE` → control returns to the planner to try again.

For now it always accepts. Later this is where anti-hallucination checks live (e.g. every
suggested market must exist in tool results) and answer-quality judging.
"""

from __future__ import annotations

from trader.core.models.schemas import AgentState, ReviewVerdict, VerifierResponse


class Verifier:
    async def __call__(self, state: AgentState) -> VerifierResponse:
        return {"review_verdict": ReviewVerdict.OK}
