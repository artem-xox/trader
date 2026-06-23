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
