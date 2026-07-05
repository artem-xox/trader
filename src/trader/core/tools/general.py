"""General read-only tools, available to every skill and to normal mode.

- `web_search`: general web search via Tavily, for context/news.
- `web_fetch`: read one page's full text.
- `current_datetime`, `calculator`, `think`: reasoning helpers.

The tools close over injected clients — they are built in the composition root
(`trader.core.bootstrap`), not at import time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.tools import BaseTool, tool

from trader.core.clients import TavilyClient
from trader.core.tools.calc import safe_eval
from trader.core.tools.schemas import (
    CalculatorInput,
    ThinkInput,
    WebFetchInput,
    WebSearchInput,
)


def build_general_tools(tavily: TavilyClient) -> list[BaseTool]:
    @tool(args_schema=WebSearchInput)
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web for current information, news, and context on any topic.

        Use this to research the real-world situation behind a market — recent news, facts,
        and developments — so you can judge whether a market's implied probability looks
        mispriced. Returns a JSON object with a synthesized `answer` and a list of `results`
        (title, url, published date, snippet).
        """
        return await tavily.search(query, max_results=max_results)

    @tool(args_schema=WebFetchInput)
    async def web_fetch(url: str) -> str:
        """Read the full readable text of a specific web page.

        Use this when you already have a URL and need its actual content — not a search.
        Good for reading a market's source/resolution reference or a full news article that
        `web_search` only surfaced a snippet of. Returns the page text (truncated).
        """
        return await tavily.fetch(url)

    @tool
    async def current_datetime() -> str:
        """Get the current date and time (UTC, ISO 8601).

        You have no built-in clock, so call this whenever the answer depends on "now" —
        e.g. how long until a market resolves, whether it is still open, or any relative
        date reasoning ("this year", "next month").
        """
        return datetime.now(timezone.utc).isoformat()

    @tool(args_schema=CalculatorInput)
    async def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression exactly.

        Use this for any non-trivial calculation instead of doing the arithmetic yourself —
        expected value, payout, edge, position sizing, probability normalization. Supports
        + - * / // % **, parentheses, and sqrt/log/ln/log10/exp/abs/round/min/max plus the
        constants pi and e. Returns the numeric result as a string.
        """
        try:
            return str(safe_eval(expression))
        except ValueError as exc:
            return f"Calculator error: {exc}"

    @tool(args_schema=ThinkInput)
    async def think(thought: str) -> str:
        """Think out loud before acting or answering — a private scratchpad.

        This fetches nothing and changes nothing; it just gives you space to lay out your
        reasoning, weigh mixed evidence, work through numbers step by step, or plan your
        next tool calls. Use it when the task is non-trivial — especially before committing
        to a stance, a probability estimate, or a final answer. One deliberate think step
        beats rushing to a shallow conclusion.
        """
        return "Noted — continue."

    return [web_search, web_fetch, current_datetime, calculator, think]
