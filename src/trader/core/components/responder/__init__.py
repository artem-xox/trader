"""Responder — synthesizes the loop's conclusion into the structured output contract.

Runs once on the "answer" branch (the planner stopped requesting tools, or the iteration
budget ran out). The active skill chooses the output schema and prompt; in normal mode a
generic `GeneralAnswer` is produced. The emitted `AIMessage` carries the human-readable
summary for the conversation history.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from trader.core.components.responder.prompts import BASE_RESPONDER_PROMPT
from trader.core.components.structured import parse_structured, structured_call
from trader.core.models.domain import GeneralAnswer, SkillResult
from trader.core.models.schemas import AgentState, ResponderResponse
from trader.core.skills.base import SkillRegistry


def _recover(raw: BaseMessage, schema: type[SkillResult]) -> SkillResult:
    """Rebuild the result from a raw message when structured parsing failed, never crashing
    the turn. Tries the tool-call args / embedded JSON (`parse_structured`); as a last resort
    keeps the raw text as the answer `summary` — so when the model replies in prose with no
    usable JSON (normal mode -> GeneralAnswer) we still return an answer.
    """
    parsed = parse_structured(raw, schema)
    if parsed is not None:
        return parsed
    content = raw.content if isinstance(raw.content, str) else str(raw.content)
    return schema(summary=content.strip() or "(no answer produced)")


class Responder:
    def __init__(self, model: BaseChatModel, registry: SkillRegistry) -> None:
        self._model = model
        self._registry = registry
        self._base_prompt = BASE_RESPONDER_PROMPT
        self._default_schema = GeneralAnswer

    async def __call__(self, state: AgentState) -> ResponderResponse:
        skill = self._registry.get(state.get("skill"))
        prompt = self._base_prompt if skill is None else skill.responder_prompt
        schema = self._default_schema if skill is None else skill.output_schema

        # Force one tool call shaped like `schema` and parse its args. We keep the raw
        # message so a rare parser hiccup is recovered (`_recover`) instead of failing the
        # turn — and, unlike `with_structured_output(include_raw=True)`, this leaves a single
        # ChatOpenAI span in the trace rather than a tree of Runnable wrappers.
        raw, parsed = await structured_call(
            self._model, schema, [SystemMessage(prompt), *state["messages"]]
        )
        result: SkillResult = parsed if parsed is not None else _recover(raw, schema)
        return {"result": result, "messages": [AIMessage(result.summary)]}
