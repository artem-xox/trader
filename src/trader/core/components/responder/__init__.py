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
    """Rebuild the result from a raw message when the structured parser failed. Prefer the
    tool-call arguments (function-calling path); fall back to decoding the first JSON object
    out of the text content, ignoring any prose tail the model appended after it."""
    tool_calls = getattr(raw, "tool_calls", None)
    if tool_calls:
        return schema.model_validate(tool_calls[0]["args"])
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

        # Function-calling returns the result as tool-call arguments, so the model cannot
        # append a prose tail after the JSON the way it did with json_schema (which raised
        # inside the model call, uncatchable). `include_raw` keeps the raw message so a
        # rare parser hiccup can be recovered instead of failing the whole turn.
        structured = self._model.with_structured_output(
            schema, method="function_calling", include_raw=True
        )
        out = await structured.ainvoke([SystemMessage(prompt), *state["messages"]])
        result: SkillResult = out["parsed"] if out["parsing_error"] is None else _recover(
            out["raw"], schema
        )
        return {"result": result, "messages": [AIMessage(result.summary)]}
