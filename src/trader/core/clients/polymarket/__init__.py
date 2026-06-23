"""Polymarket Gamma API client."""

from __future__ import annotations

import json

import httpx

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
_TIMEOUT = httpx.Timeout(15.0)


def _to_float(value: str | float | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_market(raw: dict, event_slug: str | None) -> dict | None:
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


class PolymarketClient:
    def __init__(
        self,
        base_url: str = GAMMA_BASE_URL,
        timeout: httpx.Timeout = _TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def search(self, query: str, limit: int = 8) -> str:
        params = {"q": query, "limit_per_type": max(1, min(limit, 20))}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/public-search", params=params
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return f"Polymarket search failed: {exc}"

        markets: list[dict] = []
        for event in data.get("events", []):
            event_slug = event.get("slug")
            for raw_market in event.get("markets", []):
                parsed = parse_market(raw_market, event_slug)
                if parsed:
                    markets.append(parsed)
                if len(markets) >= limit:
                    break
            if len(markets) >= limit:
                break

        if not markets:
            return f"No active Polymarket markets found for query: {query!r}."
        return json.dumps(markets, ensure_ascii=False)
