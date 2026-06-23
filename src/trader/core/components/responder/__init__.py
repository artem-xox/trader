"""Responder — synthesizes the loop's conclusion into the structured output contract.

Runs once on the "answer" branch (the planner stopped requesting tools, or the
iteration budget ran out). It re-reads the conversation and coerces it into a
`ResearchResult` via structured output, so callers consume structure, not prose. The
emitted `AIMessage` carries the human-readable summary for the conversation history.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

from trader.core.models.domain import ResearchResult
from trader.core.models.schemas import AgentState, ResponderResponse
from trader.core.prompts import RESPONDER_PROMPT


class Responder:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model.with_structured_output(ResearchResult)

    async def __call__(self, state: AgentState) -> ResponderResponse:
        messages = [SystemMessage(RESPONDER_PROMPT), *state["messages"]]
        result: ResearchResult = await self._model.ainvoke(messages)
        return {"result": result, "messages": [AIMessage(result.summary)]}
