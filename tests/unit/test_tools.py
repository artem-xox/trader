"""Tests for agent tools.

`parse_market` is pure and tested offline. The live `polymarket_search` call is marked
so it can be skipped in CI without network.
"""

from __future__ import annotations

import json

import pytest

from trader.core.clients import PolymarketClient, TavilyClient, parse_market
from trader.core.clients.polymarket import parse_market_detail
from trader.core.tools import build_tools


def test_parse_market_normalizes_prices():
    raw = {
        "id": "123",
        "question": "Will it rain?",
        "slug": "will-it-rain",
        "active": True,
        "closed": False,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.3", "0.7"]),
        "volume": "1000",
        "liquidity": "500",
        "endDate": "2026-01-01T00:00:00Z",
    }
    parsed = parse_market(raw, event_slug="weather-event")
    assert parsed["market_id"] == "123"
    assert parsed["implied_probability"] == {"Yes": 0.3, "No": 0.7}
    assert parsed["url"] == "https://polymarket.com/event/weather-event"
    assert parsed["volume"] == 1000.0


def test_parse_market_skips_closed():
    raw = {"id": "1", "closed": True, "active": False}
    assert parse_market(raw, None) is None


def test_parse_market_detail_keeps_closed_and_description():
    raw = {
        "id": "9",
        "question": "Will X happen?",
        "description": "Resolves YES if X.",
        "slug": "will-x",
        "closed": True,
        "active": False,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.4", "0.6"]),
        "volume": "10",
        "liquidity": "5",
        "endDate": "2026-01-01T00:00:00Z",
    }
    detail = parse_market_detail(raw)
    assert detail["market_id"] == "9"
    assert detail["closed"] is True  # unlike parse_market, detail keeps closed markets
    assert detail["description"] == "Resolves YES if X."
    assert detail["implied_probability"] == {"Yes": 0.4, "No": 0.6}
    assert detail["url"] == "https://polymarket.com/market/will-x"


@pytest.mark.live
@pytest.mark.asyncio
async def test_polymarket_search_live():
    polymarket_search, _ = build_tools(PolymarketClient(), TavilyClient(api_key="dummy"))
    out = await polymarket_search.ainvoke({"query": "bitcoin", "limit": 2})
    assert isinstance(out, str)
    assert "market_id" in out or "No active" in out
