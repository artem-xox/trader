"""Selector — the `skills` node. Picks at most one skill per turn.

Two stages, cheapest first:
1. Explicit slash command in the latest user message (e.g. "/find ...") → deterministic.
2. Otherwise an LLM classifies intent against the skill catalog, or returns normal mode.

The choice is recorded as a skill *name* in the state (a plain string, so the state stays
serializable for the checkpointer); the other nodes resolve the `Skill` from the registry.
An empty name means normal mode.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from trader.core.components.selector.prompts import SELECTOR_PROMPT
from trader.core.components.structured import structured_call
from trader.core.models.schemas import AgentState, Messages, SelectorResponse
from trader.core.skills.base import SkillRegistry


class _SkillChoice(BaseModel):
    skill: str = Field(description='A skill name from the catalog, or "none" for normal mode.')


def _latest_user_text(messages: Messages) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            return message.content if isinstance(message.content, str) else str(message.content)
    return ""


class Selector:
    def __init__(self, model: BaseChatModel, registry: SkillRegistry) -> None:
        self._model = model
        self._registry = registry

    async def __call__(self, state: AgentState) -> SelectorResponse:
        text = _latest_user_text(state["messages"])

        name = self._registry.match_command(text)
        if name is None:
            _, choice = await structured_call(
                self._model,
                _SkillChoice,
                [SystemMessage(SELECTOR_PROMPT.format(catalog=self._registry.catalog())), HumanMessage(text)],
            )
            name = choice.skill if choice is not None else ""

        # Normalize an unknown/"none" choice (or a failed parse) to normal mode (empty name).
        return {"skill": name if self._registry.get(name) else ""}
