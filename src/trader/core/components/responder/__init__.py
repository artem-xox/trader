"""Responder — synthesizes the loop's conclusion into the structured output contract.

Runs once on the "answer" branch (the planner stopped requesting tools, or the iteration
budget ran out). The active skill chooses the output schema and prompt; in normal mode a
generic `GeneralAnswer` is produced. The emitted `AIMessage` carries the human-readable
summary for the conversation history.
"""

from __future__ import annotations

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from trader.core.components.responder.prompts import BASE_RESPONDER_PROMPT
from trader.core.models.domain import GeneralAnswer, SkillResult
from trader.core.models.schemas import AgentState, ResponderResponse
from trader.core.skills.base import SkillRegistry


def _recover(raw: BaseMessage, schema: type[SkillResult]) -> SkillResult:
    """Rebuild the result from raw content when strict parsing fails because the model
    appended a prose tail after the JSON object. `raw_decode` reads just the first object
    and ignores whatever trailing text follows it."""
    content = raw.content if isinstance(raw.content, str) else str(raw.content)
    obj, _ = json.JSONDecoder().raw_decode(content.strip())
    return schema.model_validate(obj)


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

        # Strict json_schema constrains decoding to the schema; `include_raw` lets us
        # recover the rare case where the model still appends a prose tail after the JSON
        # (which crashed the default parser) instead of failing the whole turn.
        structured = self._model.with_structured_output(
            schema, method="json_schema", strict=True, include_raw=True
        )
        out = await structured.ainvoke([SystemMessage(prompt), *state["messages"]])
        result: SkillResult = out["parsed"] if out["parsing_error"] is None else _recover(
            out["raw"], schema
        )
        return {"result": result, "messages": [AIMessage(result.summary)]}
