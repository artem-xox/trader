"""Tests for agent tools.

`_parse_market` is pure and tested offline. The live `polymarket_search` call is marked
so it can be skipped in CI without network.
"""

from __future__ import annotations

import json

import pytest

from trader.core.tools import _parse_market, polymarket_search


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
    parsed = _parse_market(raw, event_slug="weather-event")
    assert parsed["market_id"] == "123"
    assert parsed["implied_probability"] == {"Yes": 0.3, "No": 0.7}
    assert parsed["url"] == "https://polymarket.com/event/weather-event"
    assert parsed["volume"] == 1000.0


def test_parse_market_skips_closed():
    raw = {"id": "1", "closed": True, "active": False}
    assert _parse_market(raw, None) is None


@pytest.mark.live
@pytest.mark.asyncio
async def test_polymarket_search_live():
    out = await polymarket_search.ainvoke({"query": "bitcoin", "limit": 2})
    assert isinstance(out, str)
    assert "market_id" in out or "No active" in out
