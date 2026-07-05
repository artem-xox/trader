"""Polymarket Gamma API client.

Wire-format quirks and processing live in `models.py`; this class only picks the
endpoint, builds typed request params, validates the response, and serialises the
result for the agent. Transport comes from `BaseHttpClient`.
"""

from __future__ import annotations

import json

import httpx

from trader.core.clients.base import BaseHttpClient
from trader.core.clients.polymarket.models import (
    EventsParams,
    GammaEvent,
    PublicSearchParams,
    PublicSearchResponse,
    collect_markets,
    filter_events_by_query,
    parse_market,
    parse_market_detail,
)

__all__ = ["GAMMA_BASE_URL", "PolymarketClient", "collect_markets", "parse_market", "parse_market_detail"]

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


class PolymarketClient(BaseHttpClient):
    def __init__(self, base_url: str = GAMMA_BASE_URL) -> None:
        super().__init__(base_url)

    async def search(self, query: str, limit: int = 8, tag: str | None = None) -> str:
        # When a category `tag` is given, browse that category instead of the keyword
        # index: Gamma's `/public-search` does not surface per-event sports markets
        # (e.g. a single F1 race or football match), but they are reachable by tag.
        if tag:
            return await self._search_by_tag(tag, query, limit)
        # An empty query browses the highest-volume active events across all categories —
        # the entry point for abstract asks ("most promising", "undervalued") where no
        # keyword exists to search for.
        if not query.strip():
            return await self._browse_trending(limit)

        params = PublicSearchParams(q=query, limit_per_type=max(1, min(limit, 20)))
        try:
            data = await self._get_json("/public-search", params.as_params())
        except httpx.HTTPError as exc:
            return f"Polymarket search failed: {exc}"

        markets = collect_markets(PublicSearchResponse.model_validate(data).events, limit)
        if not markets:
            return f"No active Polymarket markets found for query: {query!r}."
        return json.dumps(markets, ensure_ascii=False)

    async def _search_by_tag(self, tag: str, query: str, limit: int) -> str:
        """Browse a category by tag, then narrow to the query client-side. This is how
        a specific race or fixture is found, since the keyword index omits them."""
        try:
            events = await self._list_events(EventsParams(tag_slug=tag, limit=100))
        except httpx.HTTPError as exc:
            return f"Polymarket tag search failed: {exc}"
        if events is None:
            return f"No Polymarket events found for tag: {tag!r}."

        markets = collect_markets(filter_events_by_query(events, query), limit)
        if not markets:
            return f"No active Polymarket markets found for {query!r} in category {tag!r}."
        return json.dumps(markets, ensure_ascii=False)

    async def _browse_trending(self, limit: int) -> str:
        """List markets from the highest-volume active events, all categories."""
        try:
            events = await self._list_events(EventsParams())
        except httpx.HTTPError as exc:
            return f"Polymarket trending browse failed: {exc}"
        if events is None:
            return "No active Polymarket events found."

        markets = collect_markets(events, limit)
        if not markets:
            return "No active Polymarket markets found."
        return json.dumps(markets, ensure_ascii=False)

    async def _list_events(self, params: EventsParams) -> list[GammaEvent] | None:
        data = await self._get_json("/events", params.as_params())
        if not isinstance(data, list):
            return None
        return [GammaEvent.model_validate(e) for e in data]

    async def market(self, slug: str) -> str:
        """Fetch full detail for the market(s) at a Polymarket slug.

        Accepts a market slug or an event slug (the last path segment of a
        polymarket.com URL). An event may contain several markets; all are returned
        with full detail.
        """
        slug = slug.strip().rstrip("/").split("/")[-1]
        try:
            markets = await self._by_market_slug(slug)
            if not markets:
                markets = await self._by_event_slug(slug)
        except httpx.HTTPError as exc:
            return f"Polymarket lookup failed: {exc}"

        if not markets:
            return f"No Polymarket market found for slug: {slug!r}."
        return json.dumps(markets, ensure_ascii=False)

    async def _by_market_slug(self, slug: str) -> list[dict]:
        data = await self._get_json("/markets", {"slug": slug})
        return [parse_market_detail(m) for m in data] if isinstance(data, list) else []

    async def _by_event_slug(self, slug: str) -> list[dict]:
        data = await self._get_json("/events", {"slug": slug})
        if not (isinstance(data, list) and data):
            return []
        event = GammaEvent.model_validate(data[0])
        return [m.to_detail(event.slug) for m in event.markets]
