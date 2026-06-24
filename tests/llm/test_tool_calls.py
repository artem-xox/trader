"""LLM smoke tests for tool calling — the agent reaches for the right tool.

The find-skill + polymarket path is covered by tests/llm/test_skills.py; this file covers
normal-mode tool use.
"""

from __future__ import annotations


async def test_calls_web_search(run_with_tools, _require_tavily):
    _, tools = await run_with_tools(
        "Use the web_search tool (not polymarket_search) to find the latest news "
        "about the GTA VI release date."
    )
    assert "web_search" in tools


async def test_calls_calculator(run_with_tools):
    result, tools = await run_with_tools(
        "Use the calculator tool to compute 1234 * 5678, then tell me the result."
    )
    assert "calculator" in tools
    assert "7006652" in result.summary


async def test_calls_current_datetime(run_with_tools):
    _, tools = await run_with_tools(
        "Use the current_datetime tool to find out today's date, then tell me the year."
    )
    assert "current_datetime" in tools


async def test_calls_web_fetch(run_with_tools, _require_tavily):
    _, tools = await run_with_tools(
        "Use the web_fetch tool to read the page at https://example.com and tell me "
        "what it says."
    )
    assert "web_fetch" in tools
