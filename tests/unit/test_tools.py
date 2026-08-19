"""Tests for agent tools.

`parse_market` is pure and tested offline. The live `polymarket_search` call is marked
so it can be skipped in CI without network.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from trader.core.clients import PolymarketClient, parse_market
from trader.core.clients.polymarket import collect_markets, parse_market_detail
from trader.core.clients.polymarket.models import (
    PER_EVENT_CAP,
    TAG_PER_EVENT_CAP,
    GammaEvent,
    filter_events_by_query,
)
from trader.core.tools import build_polymarket_tools


def _raw_market(mid: str, closed: bool = False, yes_price: float = 0.5) -> dict:
    return {
        "id": mid,
        "question": f"Q{mid}",
        "slug": f"q-{mid}",
        "active": not closed,
        "closed": closed,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([str(yes_price), str(1 - yes_price)]),
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
        {
            "slug": "busy",
            "markets": [_raw_market(f"a{i}") for i in range(PER_EVENT_CAP + 10)],
        },
        {"slug": "other", "markets": [_raw_market("b1")]},
    ]
    markets = collect_markets(events, limit=PER_EVENT_CAP + 5)
    from_busy = [m for m in markets if m["market_id"].startswith("a")]
    assert len(from_busy) == PER_EVENT_CAP
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


def test_collect_markets_orders_by_interest_within_event():
    """A busy grid (e.g. one driver per market in an F1 race) must rank open questions
    first, not by id — truncating it with the per-event cap should keep the contenders,
    not an arbitrary early slice."""
    events = [
        {
            "slug": "race",
            "markets": [
                _raw_market("longshot_a", yes_price=0.002),
                _raw_market("favorite", yes_price=0.30),
                _raw_market("longshot_b", yes_price=0.01),
                _raw_market("contender", yes_price=0.18),
            ],
        }
    ]
    ids = [m["market_id"] for m in collect_markets(events, limit=4, per_event_cap=4)]
    assert ids == ["favorite", "contender", "longshot_b", "longshot_a"]


def test_collect_markets_cap_keeps_top_ranked_after_truncation():
    """Regression: a low `limit` used to return the first N markets in id order — for a
    big race grid that's N near-zero longshots. It must return the top-ranked ones."""
    events = [
        {
            "slug": "race",
            "markets": [
                _raw_market("a", yes_price=0.002),
                _raw_market("b", yes_price=0.007),
                _raw_market("c", yes_price=0.0095),
                _raw_market("antonelli", yes_price=0.295),
                _raw_market("norris", yes_price=0.18),
                _raw_market("hamilton", yes_price=0.16),
            ],
        }
    ]
    ids = [m["market_id"] for m in collect_markets(events, limit=3, per_event_cap=TAG_PER_EVENT_CAP)]
    assert ids == ["antonelli", "norris", "hamilton"]


def test_filter_events_by_query_strict_match():
    events = [
        GammaEvent(slug="dutch", title="Dutch Grand Prix: Driver Winner", markets=[]),
        GammaEvent(slug="italian", title="Italian Grand Prix: Driver Winner", markets=[]),
        GammaEvent(slug="champ", title="F1 Drivers' Champion", markets=[]),
    ]
    matched = filter_events_by_query(events, "Dutch Grand Prix")
    assert [e.slug for e in matched] == ["dutch"]


def test_filter_events_by_query_rejects_event_not_in_category():
    """Regression: a query for an event that isn't on the calendar (e.g. a race not run
    this season) must not silently fall back to an unrelated event just because both
    titles share generic category words ("Grand", "Prix") — every event in the tag
    shares those. It should come back empty so the caller gets a genuine miss."""
    events = [
        GammaEvent(slug="dutch", title="Dutch Grand Prix: Driver Winner", markets=[]),
        GammaEvent(slug="italian", title="Italian Grand Prix: Driver Winner", markets=[]),
    ]
    assert filter_events_by_query(events, "Belgian Grand Prix") == []


def test_filter_events_by_query_no_tokens_returns_all():
    events = [GammaEvent(slug="dutch", title="Dutch Grand Prix: Driver Winner", markets=[])]
    assert filter_events_by_query(events, "") == events


async def test_search_by_tag_uses_deep_cap_and_ranks_within_event():
    """A tagged search names one specific event, so it should return that event's full
    grid (up to TAG_PER_EVENT_CAP) ranked by open-question interest, not the shallow
    PER_EVENT_CAP used for keyword/trending browsing."""
    client = PolymarketClient()
    event = {
        "slug": "f1-dutch-grand-prix-winner",
        "title": "Dutch Grand Prix: Driver Winner",
        "markets": [_raw_market(f"m{i}", yes_price=0.01) for i in range(PER_EVENT_CAP + 2)]
        + [_raw_market("favorite", yes_price=0.30)],
    }
    client._list_events = AsyncMock(return_value=[GammaEvent.model_validate(event)])

    out = await client.search("Dutch Grand Prix", limit=10, tag="f1")
    markets = json.loads(out)

    assert len(markets) == PER_EVENT_CAP + 3  # all of them: below TAG_PER_EVENT_CAP
    assert markets[0]["market_id"] == "favorite"  # ranked first despite being appended last


async def test_search_by_tag_miss_lists_real_events_in_category():
    """Regression: querying an event name that doesn't exist in the tag (e.g. a race not
    on the calendar) must say so and point at real events in the category, instead of
    matching everything and returning an unrelated event's markets."""
    client = PolymarketClient()
    events = [
        GammaEvent.model_validate(
            {"slug": "dutch", "title": "Dutch Grand Prix: Driver Winner", "markets": [_raw_market("m1")]}
        ),
        GammaEvent.model_validate(
            {"slug": "italian", "title": "Italian Grand Prix: Driver Winner", "markets": [_raw_market("m2")]}
        ),
    ]
    client._list_events = AsyncMock(return_value=events)

    out = await client.search("Belgian Grand Prix", limit=3, tag="f1")

    assert "No active Polymarket markets found for 'Belgian Grand Prix'" in out
    assert "Dutch Grand Prix: Driver Winner" in out
    assert "Italian Grand Prix: Driver Winner" in out


def test_parse_market_extracts_starts_at():
    raw = {**_raw_market("55"), "gameStartTime": "2026-08-23 13:00:00+00"}
    parsed = parse_market(raw, None)
    assert parsed["starts_at"] == "2026-08-23T13:00:00+00:00"


def test_parse_market_starts_at_absent_when_not_a_scheduled_event():
    parsed = parse_market(_raw_market("56"), None)
    assert "starts_at" not in parsed


def test_parse_market_carries_event_title():
    raw = _raw_market("57")
    parsed = GammaEvent.model_validate(
        {"slug": "dutch", "title": "Dutch Grand Prix: Driver Winner", "markets": [raw]}
    ).markets[0].to_summary("dutch", "Dutch Grand Prix: Driver Winner")
    assert parsed["event"] == "Dutch Grand Prix: Driver Winner"


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
