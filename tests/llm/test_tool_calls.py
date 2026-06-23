"""LLM smoke tests for tool calling — the agent reaches for the right tool."""

from __future__ import annotations


async def test_calls_polymarket_search(run_with_tools):
    result, tools = await run_with_tools(
        "Find interesting Polymarket bets about bitcoin price in 2026."
    )
    assert "polymarket_search" in tools
    # Real suggestions must carry market ids that came from the tools (verifier-enforced).
    assert all(s.market_id for s in result.suggestions)


async def test_calls_web_search(run_with_tools, _require_tavily):
    _, tools = await run_with_tools(
        "Use the web_search tool (not polymarket_search) to find the latest news "
        "about the GTA VI release date."
    )
    assert "web_search" in tools
