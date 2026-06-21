"""Agent tools.

Two real tools for the first iteration:
- `polymarket_search`: active markets via the public Gamma API (no auth).
- `web_search`: general web search via Tavily, for context/news around a topic.

Both return JSON strings so the model reasons over a consistent, compact shape. Prices
are normalized to implied probabilities.
"""

from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool
from tavily import AsyncTavilyClient

from trader.common.config import get_settings

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
_TIMEOUT = httpx.Timeout(15.0)


def _to_float(value: str | float | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_market(raw: dict, event_slug: str | None) -> dict | None:
    """Reduce a raw Gamma market into the compact shape the agent reasons over."""
    if raw.get("closed") or not raw.get("active", True):
        return None

    outcomes = raw.get("outcomes")
    prices = raw.get("outcomePrices")
    # Gamma returns these as JSON-encoded strings.
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    if isinstance(prices, str):
        prices = json.loads(prices)

    implied = None
    if outcomes and prices and len(outcomes) == len(prices):
        implied = {o: _to_float(p) for o, p in zip(outcomes, prices)}

    slug = raw.get("slug")
    url = (
        f"https://polymarket.com/event/{event_slug}"
        if event_slug
        else (f"https://polymarket.com/market/{slug}" if slug else None)
    )

    return {
        "market_id": raw.get("id"),
        "question": raw.get("question"),
        "url": url,
        "implied_probability": implied,
        "volume": _to_float(raw.get("volume")),
        "liquidity": _to_float(raw.get("liquidity")),
        "ends_at": raw.get("endDate"),
    }


@tool
async def polymarket_search(query: str, limit: int = 8) -> str:
    """Search active Polymarket prediction markets matching a topic or keyword.

    Returns a JSON list of markets with their question, current implied probabilities
    per outcome, traded volume, liquidity, end date, and a link. Use this to find real
    markets before suggesting any bet — never invent markets.
    """
    params = {"q": query, "limit_per_type": max(1, min(limit, 20))}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{GAMMA_BASE_URL}/public-search", params=params)
        resp.raise_for_status()
        data = resp.json()

    markets: list[dict] = []
    for event in data.get("events", []):
        event_slug = event.get("slug")
        for raw_market in event.get("markets", []):
            parsed = _parse_market(raw_market, event_slug)
            if parsed:
                markets.append(parsed)
            if len(markets) >= limit:
                break
        if len(markets) >= limit:
            break

    if not markets:
        return f"No active Polymarket markets found for query: {query!r}."
    return json.dumps(markets, ensure_ascii=False)


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information, news, and context on any topic.

    Use this to research the real-world situation behind a market — recent news, facts,
    and developments — so you can judge whether a market's implied probability looks
    mispriced. Returns a JSON object with a synthesized `answer` and a list of `results`
    (title, url, published date, snippet).
    """
    client = AsyncTavilyClient(api_key=get_settings().tavily_api_key)
    resp = await client.search(
        query,
        max_results=max(1, min(max_results, 10)),
        search_depth="basic",
        include_answer=True,
    )

    results = [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "published_date": r.get("published_date"),
            "snippet": r.get("content"),
        }
        for r in resp.get("results", [])
    ]
    if not results:
        return f"No web results found for query: {query!r}."
    return json.dumps(
        {"answer": resp.get("answer"), "results": results}, ensure_ascii=False
    )


ALL_TOOLS = [polymarket_search, web_search]
