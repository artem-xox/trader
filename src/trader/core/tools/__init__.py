"""Agent tools.

Two real tools for the first iteration:
- `polymarket_search`: active markets via the public Gamma API (no auth).
- `web_search`: general web search via Tavily, for context/news around a topic.

Both return JSON strings so the model reasons over a consistent, compact shape. Prices
are normalized to implied probabilities. The tools close over injected clients — they
are built in the composition root (`trader.core.bootstrap`), not at import time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.tools import BaseTool, tool

from trader.core.clients import PolymarketClient, TavilyClient
from trader.core.tools.calc import safe_eval
from trader.core.tools.schemas import (
    CalculatorInput,
    PolymarketMarketInput,
    PolymarketSearchInput,
    WebFetchInput,
    WebSearchInput,
)


def build_tools(polymarket: PolymarketClient, tavily: TavilyClient) -> list[BaseTool]:
    @tool(args_schema=PolymarketSearchInput)
    async def polymarket_search(query: str, limit: int = 8) -> str:
        """Search active Polymarket prediction markets matching a topic or keyword.

        Markets are indexed in English, so search with short English keywords for the most
        distinctive entity (a name, e.g. "Jesus", "Bitcoin"), not a long literal phrase or a
        non-English one. If a query returns nothing relevant, reformulate and try again.

        Returns a JSON list of markets with their question, current implied probabilities
        per outcome, traded volume, liquidity, end date, and a link. Use this to find real
        markets before suggesting any bet — never invent markets.
        """
        return await polymarket.search(query, limit=limit)

    @tool(args_schema=PolymarketMarketInput)
    async def polymarket_market(slug: str) -> str:
        """Fetch full detail for a specific Polymarket market by its slug.

        The slug is the last path segment of a polymarket.com URL. Returns a JSON list of
        the market(s) at that slug with question, resolution criteria (`description`),
        current implied probabilities, volume, liquidity, end date, and closed flag. Use
        this to analyze a single market the user pointed to.
        """
        return await polymarket.market(slug)

    @tool(args_schema=WebSearchInput)
    async def web_search(query: str, max_results: int = 5) -> str:
        """Search the web for current information, news, and context on any topic.

        Use this to research the real-world situation behind a market — recent news, facts,
        and developments — so you can judge whether a market's implied probability looks
        mispriced. Returns a JSON object with a synthesized `answer` and a list of `results`
        (title, url, published date, snippet).
        """
        return await tavily.search(query, max_results=max_results)

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

    @tool(args_schema=WebFetchInput)
    async def web_fetch(url: str) -> str:
        """Read the full readable text of a specific web page.

        Use this when you already have a URL and need its actual content — not a search.
        Good for reading a market's source/resolution reference or a full news article that
        `web_search` only surfaced a snippet of. Returns the page text (truncated).
        """
        return await tavily.fetch(url)

    return [
        polymarket_search,
        polymarket_market,
        web_search,
        current_datetime,
        calculator,
        web_fetch,
    ]
