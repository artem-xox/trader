"""Offline tests for the agent's progress streaming (Phase B live status)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from trader.common.config import Settings
from trader.core.agents.react import ReActAgent, _arg_hint, _status_for
from trader.core.models.domain import GeneralAnswer
from trader.core.models.schemas import GuardVerdict, ReviewVerdict


def test_arg_hint_prefers_query_and_skips_ids():
    assert _arg_hint({"query": "bitcoin"}) == "bitcoin"
    assert _arg_hint({"slug": "will-x-happen"}) == "will-x-happen"
    assert _arg_hint({"token_id": "0xabc"}) is None  # ids are noise, not a useful hint
    assert _arg_hint({}) is None


def test_status_for_planner_tool_call_carries_hint():
    update = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "btc"}, "id": "c1"}])
        ]
    }
    event = _status_for("planner", update)
    assert (event.label, event.detail) == ("tool:web_search", "btc")


def test_status_for_silent_and_terminal_nodes():
    assert _status_for("guard", {"guard_verdict": GuardVerdict.ALLOW}) is None
    assert _status_for("executor", {"messages": []}) is None
    assert _status_for("verifier", {"review_verdict": ReviewVerdict.OK}) is None
    assert _status_for("verifier", {"review_verdict": ReviewVerdict.REVISE}).label == "revise"
    assert _status_for("planner", {"messages": [AIMessage("done")]}) is None  # drafted an answer


def _stub_agent() -> ReActAgent:
    """A ReActAgent whose nodes drive one tool round then an answer — no LLM/network."""

    async def selector(state):
        return {"skill": "find"}

    async def planner(state):
        i = state.get("iteration", 0)
        msg = (
            AIMessage(content="", tool_calls=[{"name": "polymarket_search", "args": {"query": "btc"}, "id": "c1"}])
            if i == 0
            else AIMessage("here you go")
        )
        return {"messages": [msg], "iteration": i + 1}

    async def guard(state):
        return {"guard_verdict": GuardVerdict.ALLOW}

    async def executor(state):
        return {"messages": [ToolMessage(content="[]", name="polymarket_search", tool_call_id="c1")]}

    async def responder(state):
        return {"result": GeneralAnswer(summary="ok"), "messages": [AIMessage("ok")]}

    async def verifier(state):
        return {"review_verdict": ReviewVerdict.OK}

    return ReActAgent(
        selector=selector,
        planner=planner,
        guard=guard,
        executor=executor,
        responder=responder,
        verifier=verifier,
        checkpointer=InMemorySaver(),
        settings=Settings(agent_max_iterations=8),
    )


async def test_astream_emits_statuses_then_final():
    events = [ev async for ev in _stub_agent().astream([HumanMessage("/find btc")], thread_id="t1")]

    assert [(e.kind, e.label) for e in events[:-1]] == [
        ("status", "skill:find"),
        ("status", "tool:polymarket_search"),
        ("status", "synthesize"),
    ]
    assert events[1].detail == "btc"
    assert events[-1].kind == "final"
    assert events[-1].result.summary == "ok"
