"""Shared setup for LLM smoke tests.

These tests make real model calls. They are auto-marked `llm` and skipped when no
`OPENAI_API_KEY` is available, so they never run (or cost money) by accident.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

_LLM_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Mark every test that lives under tests/llm as `llm`."""
    for item in items:
        if _LLM_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.llm)


@pytest.fixture(autouse=True)
def _require_openai():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


@pytest.fixture
def _require_tavily():
    if not os.getenv("TAVILY_API_KEY"):
        pytest.skip("TAVILY_API_KEY not set")


@pytest.fixture(scope="module")
def agent():
    from trader.core.agents.builtin import BuiltinAgent

    return BuiltinAgent()


@pytest.fixture
def run_with_tools(agent):
    """Run the agent on a prompt, returning (final_text, list_of_tool_names_called)."""

    async def _run(prompt: str) -> tuple[str, list[str]]:
        result = await agent._graph.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": 16},
        )
        messages = result["messages"]
        tools = [m.name for m in messages if getattr(m, "type", None) == "tool"]
        final = messages[-1].content
        final = final if isinstance(final, str) else str(final)
        return final, tools

    return _run
