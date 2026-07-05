"""Tests for agent tools.

`parse_market` is pure and tested offline. The live `polymarket_search` call is marked
so it can be skipped in CI without network.
"""

from __future__ import annotations

import json

import pytest

from trader.core.clients import PolymarketClient, parse_market
from trader.core.clients.polymarket import collect_markets, parse_market_detail
from trader.core.tools import build_polymarket_tools


def _raw_market(mid: str, closed: bool = False) -> dict:
    return {
        "id": mid,
        "question": f"Q{mid}",
        "slug": f"q-{mid}",
        "active": not closed,
        "closed": closed,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.5", "0.5"]),
        "volume": "100",
        "liquidity": "50",
        "endDate": "2026-12-01T00:00:00Z",
    }


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


def test_parse_market_extracts_volume_24h():
    raw = {**_raw_market("42"), "volume24hr": "2500.5"}
    parsed = parse_market(raw, None)
    assert parsed["volume_24h"] == 2500.5


def test_parse_market_volume_24h_absent():
    parsed = parse_market(_raw_market("43"), None)
    assert parsed["volume_24h"] is None


def test_collect_markets_caps_per_event():
    """One busy event (many near-zero candidate markets) must not fill the whole list."""
    events = [
        {"slug": "busy", "markets": [_raw_market(f"a{i}") for i in range(10)]},
        {"slug": "other", "markets": [_raw_market("b1")]},
    ]
    markets = collect_markets(events, limit=8)
    from_busy = [m for m in markets if m["market_id"].startswith("a")]
    assert len(from_busy) == 3  # _PER_EVENT_CAP
    assert any(m["market_id"] == "b1" for m in markets)


def test_collect_markets_respects_limit():
    events = [{"slug": f"e{i}", "markets": [_raw_market(f"m{i}")]} for i in range(10)]
    assert len(collect_markets(events, limit=4)) == 4


def test_collect_markets_skips_closed_within_cap():
    """Closed markets don't consume the per-event cap."""
    events = [
        {
            "slug": "mixed",
            "markets": [
                _raw_market("dead1", closed=True),
                _raw_market("dead2", closed=True),
                _raw_market("live1"),
                _raw_market("live2"),
            ],
        }
    ]
    ids = [m["market_id"] for m in collect_markets(events, limit=8)]
    assert ids == ["live1", "live2"]


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
    tools = build_polymarket_tools(PolymarketClient())
    out = await tools.search.ainvoke({"query": "bitcoin", "limit": 2})
    assert isinstance(out, str)
    assert "market_id" in out or "No active" in out


@pytest.mark.live
@pytest.mark.asyncio
async def test_polymarket_search_surfaces_active_over_closed_live():
    """Regression: for queries whose top-ranked Gamma results are resolved markets (e.g.
    "nvidia"), search must still surface the active ones (via `events_status=active`) rather
    than falsely reporting no markets."""
    out = await PolymarketClient().search("nvidia", limit=5)
    assert "market_id" in out, out
