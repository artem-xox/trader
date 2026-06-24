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


def _market_url(raw: dict, event_slug: str | None) -> str | None:
    if event_slug:
        return f"https://polymarket.com/event/{event_slug}"
    slug = raw.get("slug")
    return f"https://polymarket.com/market/{slug}" if slug else None


def _implied(raw: dict) -> dict | None:
    outcomes = raw.get("outcomes")
    prices = raw.get("outcomePrices")
    # Gamma returns these as JSON-encoded strings.
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    if isinstance(prices, str):
        prices = json.loads(prices)
    if outcomes and prices and len(outcomes) == len(prices):
        return {o: _to_float(p) for o, p in zip(outcomes, prices)}
    return None


def parse_market_detail(raw: dict, event_slug: str | None = None) -> dict:
    """Full detail for a single market, including resolution criteria. Unlike
    `parse_market` this keeps closed/inactive markets — the user asked for this one."""
    return {
        "market_id": raw.get("id"),
        "question": raw.get("question"),
        "description": raw.get("description"),
        "url": _market_url(raw, event_slug),
        "implied_probability": _implied(raw),
        "volume": _to_float(raw.get("volume")),
        "liquidity": _to_float(raw.get("liquidity")),
        "ends_at": raw.get("endDate"),
        "closed": bool(raw.get("closed")),
    }


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
        # `events_status=active` is required: without it Gamma ranks resolved/old markets
        # first and can bury (or omit) the active ones entirely — e.g. "nvidia" otherwise
        # returns only closed markets and looks like "no markets". The `active`/`closed`
        # params have no effect on this endpoint; `events_status` is the one that works.
        params = {
            "q": query,
            "limit_per_type": max(1, min(limit, 20)),
            "events_status": "active",
        }
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

    async def market(self, slug: str) -> str:
        """Fetch full detail for the market(s) at a Polymarket slug.

        Accepts a market slug or an event slug (the last path segment of a polymarket.com
        URL). An event may contain several markets; all are returned with full detail.
        """
        slug = slug.strip().rstrip("/").split("/")[-1]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                markets = await self._by_market_slug(client, slug)
                if not markets:
                    markets = await self._by_event_slug(client, slug)
        except httpx.HTTPError as exc:
            return f"Polymarket lookup failed: {exc}"

        if not markets:
            return f"No Polymarket market found for slug: {slug!r}."
        return json.dumps(markets, ensure_ascii=False)

    async def _by_market_slug(self, client: httpx.AsyncClient, slug: str) -> list[dict]:
        resp = await client.get(f"{self._base_url}/markets", params={"slug": slug})
        resp.raise_for_status()
        data = resp.json()
        return [parse_market_detail(m) for m in data] if isinstance(data, list) else []

    async def _by_event_slug(self, client: httpx.AsyncClient, slug: str) -> list[dict]:
        resp = await client.get(f"{self._base_url}/events", params={"slug": slug})
        resp.raise_for_status()
        events = resp.json()
        if not (isinstance(events, list) and events):
            return []
        event = events[0]
        return [parse_market_detail(m, event.get("slug")) for m in event.get("markets", [])]
