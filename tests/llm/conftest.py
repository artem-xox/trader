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
def prebuilt_agent():
    from trader.core.agents.builtin import BuiltinAgent

    return BuiltinAgent()


@pytest.fixture(scope="module")
def react_agent():
    from trader.core.bootstrap import build_agent

    return build_agent()


@pytest.fixture(
    scope="module",
    params=["prebuilt_agent", "react_agent"],
    ids=["prebuilt", "react"],
)
def agent(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def invoke_prompt(agent):
    """Run the agent on a single user prompt and return the final answer text."""

    async def _invoke(prompt: str) -> str:
        result = await agent._graph.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": agent._settings.agent_max_iterations * 2},
        )
        final = result["messages"][-1].content
        return final if isinstance(final, str) else str(final)

    return _invoke


@pytest.fixture
def run_with_tools(agent):
    """Run the agent on a prompt, returning (final_text, list_of_tool_names_called)."""

    async def _run(prompt: str) -> tuple[str, list[str]]:
        result = await agent._graph.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": agent._settings.agent_max_iterations * 2},
        )
        messages = result["messages"]
        tools = [m.name for m in messages if getattr(m, "type", None) == "tool"]
        final = messages[-1].content
        final = final if isinstance(final, str) else str(final)
        return final, tools

    return _run
