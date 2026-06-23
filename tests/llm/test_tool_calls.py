"""LLM smoke tests for tool calling — the agent reaches for the right tool."""

from __future__ import annotations


async def test_calls_polymarket_search(run_with_tools):
    final, tools = await run_with_tools(
        "Find interesting Polymarket bets about bitcoin price in 2026."
    )
    assert "polymarket_search" in tools
    # A real suggestion should link to polymarket.
    assert "polymarket.com" in final.lower()


async def test_calls_web_search(run_with_tools):
    _, tools = await run_with_tools(
        "Search the web for the latest news about the GTA VI release date."
    )
    assert "web_search" in tools
