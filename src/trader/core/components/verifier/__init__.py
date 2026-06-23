"""Verifier — final gate that checks the structured answer before it leaves the loop.

Contract:
- Input: `state["result"]` is the `ResearchResult` produced by the responder.
- Output: `{"review_verdict": ReviewVerdict, ...}`.
  - `ReviewVerdict.OK` → the result is returned to the caller.
  - `ReviewVerdict.REVISE` → a feedback message is appended and control returns to the
    planner to try again.

The check it enforces is anti-hallucination: every suggested `market_id` must actually
appear in the polymarket tool results gathered during the loop. This is the guarantee
that makes the recommendations trustworthy. Results without `suggestions` (e.g. normal
mode's `GeneralAnswer`) have nothing to validate and pass through.
"""

from __future__ import annotations

import json

from langchain_core.messages import SystemMessage

from trader.core.models.schemas import AgentState, ReviewVerdict, VerifierResponse


def _market_ids_seen(state: AgentState) -> set[str]:
    """Collect every market_id returned by any tool during this run."""
    ids: set[str] = set()
    for message in state["messages"]:
        if getattr(message, "type", None) != "tool":
            continue
        try:
            markets = json.loads(message.content)
        except (TypeError, ValueError):
            continue  # tool returned an error/"no results" string, not JSON
        if isinstance(markets, list):
            ids.update(str(m["market_id"]) for m in markets if isinstance(m, dict) and m.get("market_id"))
    return ids


class Verifier:
    async def __call__(self, state: AgentState) -> VerifierResponse:
        result = state.get("result")
        referenced = result.referenced_market_ids() if result else []
        if not referenced:
            return {"review_verdict": ReviewVerdict.OK}

        seen = _market_ids_seen(state)
        invented = [mid for mid in referenced if mid not in seen]
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
