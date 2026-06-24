"""Agent tools.

Two real tools for the first iteration:
- `polymarket_search`: active markets via the public Gamma API (no auth).
- `web_search`: general web search via Tavily, for context/news around a topic.

Both return JSON strings so the model reasons over a consistent, compact shape. Prices
are normalized to implied probabilities. The tools close over injected clients — they
are built in the composition root (`trader.core.bootstrap`), not at import time.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from trader.core.clients import PolymarketClient, TavilyClient
from trader.core.tools.schemas import (
    PolymarketMarketInput,
    PolymarketSearchInput,
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

    return [polymarket_search, polymarket_market, web_search]
