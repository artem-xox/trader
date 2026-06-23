"""The trading agent: a ReAct loop over the agent tools.

For the first iteration this wraps LangGraph's prebuilt ReAct agent. The `TradingAgent`
class is the single entry point the HTTP app (and tests) call, so we can later swap the
internals for a custom graph without touching callers.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from trader.core.agents.base import BaseAgent
from trader.core.prompts import SYSTEM_PROMPT
from trader.core.tools import ALL_TOOLS


class BuiltinAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__()
        model = ChatOpenAI(
            model=self._settings.openai_model,
            api_key=self._settings.openai_api_key,
            temperature=0.4,
        )
        self._graph = create_react_agent(
            model,
            tools=ALL_TOOLS,
            prompt=SYSTEM_PROMPT,
            name="prebuilt-react",
        )

    async def invoke(self, message: str) -> str:
        """Run the ReAct loop for a single user message and return the final answer."""
        result = await self._graph.ainvoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"recursion_limit": self._settings.agent_max_iterations * 2},
        )
        final = result["messages"][-1]
        return final.content if isinstance(final.content, str) else str(final.content)
