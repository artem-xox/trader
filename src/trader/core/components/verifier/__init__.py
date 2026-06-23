"""Verifier — final gate that checks the structured answer before it leaves the loop.

Contract:
- Input: `state["result"]` is the `ResearchResult` produced by the responder.
- Output: `{"review_verdict": ReviewVerdict, ...}`.
  - `ReviewVerdict.OK` → the result is returned to the caller.
  - `ReviewVerdict.REVISE` → a feedback message is appended and control returns to the
    planner to try again.

The check it enforces is anti-hallucination: every suggested `market_id` must actually
appear in the polymarket tool results gathered during the loop. This is the guarantee
that makes the recommendations trustworthy.
"""

from __future__ import annotations

import json

from langchain_core.messages import SystemMessage

from trader.core.models.schemas import AgentState, ReviewVerdict, VerifierResponse

_POLYMARKET_TOOL = "polymarket_search"


def _market_ids_seen(state: AgentState) -> set[str]:
    """Collect every market_id returned by the polymarket tool during this run."""
    ids: set[str] = set()
    for message in state["messages"]:
        if getattr(message, "type", None) != "tool" or message.name != _POLYMARKET_TOOL:
            continue
        try:
            markets = json.loads(message.content)
        except (TypeError, ValueError):
            continue  # tool returned an error/"no results" string, not JSON
        if isinstance(markets, list):
            ids.update(str(m["market_id"]) for m in markets if m.get("market_id"))
    return ids


class Verifier:
    async def __call__(self, state: AgentState) -> VerifierResponse:
        result = state.get("result")
        if result is None or not result.suggestions:
            return {"review_verdict": ReviewVerdict.OK}

        seen = _market_ids_seen(state)
        invented = [s.market_id for s in result.suggestions if s.market_id not in seen]
        if invented:
            return {
                "review_verdict": ReviewVerdict.REVISE,
                "messages": [
                    SystemMessage(
                        "These market_ids were not returned by any polymarket_search call "
                        f"and must not be suggested: {invented}. Remove them or call "
                        "polymarket_search again to find real markets."
                    )
                ],
            }
        return {"review_verdict": ReviewVerdict.OK}
