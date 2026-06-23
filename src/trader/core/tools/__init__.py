"""Agent tools.

Two real tools for the first iteration:
- `polymarket_search`: active markets via the public Gamma API (no auth).
- `web_search`: general web search via Tavily, for context/news around a topic.

Both return JSON strings so the model reasons over a consistent, compact shape. Prices
are normalized to implied probabilities.
"""

from __future__ import annotations

from langchain_core.tools import tool

from trader.common.config import get_settings
from trader.core.clients import PolymarketClient, TavilyClient
from trader.core.tools.schemas import PolymarketSearchInput, WebSearchInput

_polymarket = PolymarketClient()
_tavily = TavilyClient(api_key=get_settings().tavily_api_key)


@tool(args_schema=PolymarketSearchInput)
async def polymarket_search(query: str, limit: int = 8) -> str:
    """Search active Polymarket prediction markets matching a topic or keyword.

    Returns a JSON list of markets with their question, current implied probabilities
    per outcome, traded volume, liquidity, end date, and a link. Use this to find real
    markets before suggesting any bet — never invent markets.
    """
    return await _polymarket.search(query, limit=limit)


@tool(args_schema=WebSearchInput)
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information, news, and context on any topic.

    Use this to research the real-world situation behind a market — recent news, facts,
    and developments — so you can judge whether a market's implied probability looks
    mispriced. Returns a JSON object with a synthesized `answer` and a list of `results`
    (title, url, published date, snippet).
    """
    return await _tavily.search(query, max_results=max_results)


ALL_TOOLS = [polymarket_search, web_search]
