"""Offline test for the tool-trajectory projection used by tool-use evaluation.

`_tool_trajectory` reconstructs the ordered (name, args, result) of a run from the message
history. It is the deterministic input the `tool_use` LLM-judge reasons over, so it is
worth pinning without a live run.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.eval.runner import _tool_trajectory


def test_trajectory_pairs_calls_with_results_in_order():
    messages = [
        HumanMessage("find bitcoin markets"),
        AIMessage(
            content="",
            tool_calls=[{"name": "polymarket_search", "args": {"query": "bitcoin"}, "id": "c1"}],
        ),
        ToolMessage(content='[{"market_id": "1"}]', name="polymarket_search", tool_call_id="c1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "web_search", "args": {"query": "btc news"}, "id": "c2"}],
        ),
        ToolMessage(content='{"answer": "..."}', name="web_search", tool_call_id="c2"),
        AIMessage(content="done"),
    ]

    trajectory = _tool_trajectory(messages)

    assert [c["name"] for c in trajectory] == ["polymarket_search", "web_search"]
    assert trajectory[0]["args"] == {"query": "bitcoin"}
    assert trajectory[0]["result"] == '[{"market_id": "1"}]'
    assert "id" not in trajectory[0]  # internal call id is not leaked into the projection


def test_trajectory_empty_when_no_tools():
    messages = [HumanMessage("hi"), AIMessage(content="hello")]
    assert _tool_trajectory(messages) == []
