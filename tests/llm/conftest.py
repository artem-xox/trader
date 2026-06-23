"""Shared setup for LLM smoke tests.

These tests make real model calls. They are auto-marked `llm` and skipped when no
`OPENAI_API_KEY` is available, so they never run (or cost money) by accident.
"""

from __future__ import annotations

import os
import uuid
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
    from trader.core.bootstrap import build_agent

    return build_agent()


@pytest.fixture
def invoke_prompt(agent):
    """Run the agent on a single user prompt and return the result summary text."""
    from langchain_core.messages import HumanMessage

    async def _invoke(prompt: str) -> str:
        result = await agent.invoke([HumanMessage(prompt)], thread_id=uuid.uuid4().hex)
        return result.summary

    return _invoke


@pytest.fixture
def run_with_tools(agent):
    """Run the agent on a prompt, returning (result, list_of_tool_names_called).

    Reaches into the compiled graph (not the public API) to inspect which tools fired.
    """
    from langchain_core.messages import HumanMessage

    async def _run(prompt: str):
        state = await agent._graph.ainvoke(
            {"messages": [HumanMessage(prompt)]},
            config={
                "recursion_limit": agent._settings.agent_max_iterations * 6 + 10,
                "configurable": {"thread_id": uuid.uuid4().hex},
            },
        )
        tools = [m.name for m in state["messages"] if getattr(m, "type", None) == "tool"]
        return state["result"], tools

    return _run
