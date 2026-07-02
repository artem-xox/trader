"""Offline tests for the responder's normal-mode passthrough (no extra LLM call)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from trader.core.components.responder import Responder
from trader.core.models.domain import GeneralAnswer
from trader.core.skills.base import Skill, SkillRegistry


class _FakeModel:
    """Records every `ainvoke` call so tests can assert whether the model ran."""

    def __init__(self, response: AIMessage) -> None:
        self._response = response
        self.calls: list = []

    def bind_tools(self, tools, tool_choice=None):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self._response


def _skill(name: str = "find") -> Skill:
    return Skill(
        name=name,
        triggers=(name,),
        description="",
        planner_prompt="",
        guard_prompt="",
        responder_prompt="respond",
        output_schema=GeneralAnswer,
        tools=(),
    )


async def test_normal_mode_reuses_drafted_answer_without_calling_model():
    model = _FakeModel(AIMessage("should not be used"))
    responder = Responder(model, SkillRegistry([]))
    state = {"messages": [AIMessage("the drafted final answer")], "skill": ""}

    result = await responder(state)

    assert model.calls == []
    assert result["result"].summary == "the drafted final answer"
    assert result["messages"] == []


async def test_normal_mode_still_calls_model_when_budget_ran_out():
    # Executor routed straight to the responder before the planner drafted anything —
    # the last message is a tool result, not an answer, so synthesis is still needed.
    reply = AIMessage(
        content="",
        tool_calls=[{"name": "GeneralAnswer", "args": {"summary": "synthesized"}, "id": "1"}],
    )
    model = _FakeModel(reply)
    responder = Responder(model, SkillRegistry([]))
    state = {
        "messages": [ToolMessage(content="[]", name="web_search", tool_call_id="c1")],
        "skill": "",
    }

    result = await responder(state)

    assert len(model.calls) == 1
    assert result["result"].summary == "synthesized"


async def test_skill_mode_calls_model_even_with_a_drafted_answer():
    reply = AIMessage(
        content="",
        tool_calls=[{"name": "GeneralAnswer", "args": {"summary": "skill answer"}, "id": "1"}],
    )
    model = _FakeModel(reply)
    responder = Responder(model, SkillRegistry([_skill()]))
    state = {"messages": [AIMessage("draft")], "skill": "find"}

    result = await responder(state)

    assert len(model.calls) == 1
    assert result["result"].summary == "skill answer"
