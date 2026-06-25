"""Offline tests for the CLOB client: parsers and derived metrics.

All tests run against fixed fixtures — no network, no LLM.
"""

from __future__ import annotations

import json
import math

import pytest

from trader.core.clients.clob import (
    best_ask,
    best_bid,
    depth_within_2_ticks,
    mid,
    parse_book,
    parse_history,
    realised_vol,
    slippage_from_book,
    spread_bps,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RAW_BOOK = {
    "market": "0xabc",
    "asset_id": "111",
    "timestamp": "2026-06-25T12:00:00Z",
    "tick_size": 0.01,
    "min_order_size": 5.0,
    "neg_risk": False,
    "last_trade_price": "0.55",
    # bids: intentionally unsorted to test sorting
    "bids": [
        {"price": "0.53", "size": "100"},
        {"price": "0.54", "size": "200"},
        {"price": "0.52", "size": "50"},
    ],
    # asks: intentionally unsorted
    "asks": [
        {"price": "0.57", "size": "80"},
        {"price": "0.56", "size": "150"},
        {"price": "0.58", "size": "60"},
    ],
}

_RAW_HISTORY = {
    "history": [
        {"t": 1000, "p": 0.50},
        {"t": 1060, "p": 0.52},
        {"t": 1120, "p": 0.54},
        {"t": 1180, "p": 0.48},
        {"t": 1240, "p": 0.46},
    ]
}


# ---------------------------------------------------------------------------
# parse_book
# ---------------------------------------------------------------------------


def test_parse_book_sorts_bids_best_first():
    book = parse_book(_RAW_BOOK)
    prices = [lv.price for lv in book.bids]
    assert prices == sorted(prices, reverse=True), "bids must be sorted best-first (highest)"


def test_parse_book_sorts_asks_best_first():
    book = parse_book(_RAW_BOOK)
    prices = [lv.price for lv in book.asks]
    assert prices == sorted(prices), "asks must be sorted best-first (lowest)"


def test_parse_book_float_types():
    book = parse_book(_RAW_BOOK)
    assert isinstance(book.bids[0].price, float)
    assert isinstance(book.bids[0].size, float)
    assert isinstance(book.last_trade_price, float)


def test_parse_book_metadata():
    book = parse_book(_RAW_BOOK)
    assert book.market == "0xabc"
    assert book.tick_size == 0.01
    assert book.min_order_size == 5.0


def test_parse_book_empty_levels():
    book = parse_book({"market": "x", "asset_id": "y", "timestamp": "", "tick_size": 0.01,
                       "min_order_size": 5.0, "bids": [], "asks": []})
    assert book.bids == []
    assert book.asks == []


# ---------------------------------------------------------------------------
# parse_history
# ---------------------------------------------------------------------------


def test_parse_history_returns_tuples():
    history = parse_history(_RAW_HISTORY)
    assert len(history) == 5
    assert all(isinstance(t, int) and isinstance(p, float) for t, p in history)


def test_parse_history_empty():
    assert parse_history({}) == []
    assert parse_history({"history": []}) == []


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------


def test_best_bid_ask():
    book = parse_book(_RAW_BOOK)
    assert best_bid(book) == pytest.approx(0.54)
    assert best_ask(book) == pytest.approx(0.56)


def test_mid():
    book = parse_book(_RAW_BOOK)
    assert mid(book) == pytest.approx(0.55)


def test_spread_bps():
    book = parse_book(_RAW_BOOK)
    # spread = 0.56 - 0.54 = 0.02; mid = 0.55; bps = 0.02/0.55 * 10000 ≈ 363.6
    expected = 0.02 / 0.55 * 10_000
    assert spread_bps(book) == pytest.approx(expected, rel=1e-4)


def test_spread_bps_empty_book():
    book = parse_book({"market": "x", "asset_id": "y", "timestamp": "", "tick_size": 0.01,
                       "min_order_size": 5.0, "bids": [], "asks": []})
    assert spread_bps(book) is None


def test_depth_within_2_ticks():
    book = parse_book(_RAW_BOOK)
    # mid = 0.55, tick = 0.01, window = [0.53, 0.57]
    # bids in window: 0.54 (200), 0.53 (100) → 300
    # asks in window: 0.56 (150), 0.57 (80) → 230
    # total = 530
    d = depth_within_2_ticks(book, side="both")
    assert d == pytest.approx(530.0)


def test_depth_within_2_ticks_bids_only():
    book = parse_book(_RAW_BOOK)
    assert depth_within_2_ticks(book, side="bids") == pytest.approx(300.0)


def test_depth_within_2_ticks_asks_only():
    book = parse_book(_RAW_BOOK)
    assert depth_within_2_ticks(book, side="asks") == pytest.approx(230.0)


def test_realised_vol():
    history = parse_history(_RAW_HISTORY)
    vol = realised_vol(history)
    assert vol is not None
    prices = [0.50, 0.52, 0.54, 0.48, 0.46]
    mean = sum(prices) / len(prices)
    expected = math.sqrt(sum((p - mean) ** 2 for p in prices) / len(prices))
    assert vol == pytest.approx(expected, rel=1e-6)


def test_realised_vol_single_point():
    assert realised_vol([(1000, 0.5)]) is None


def test_realised_vol_empty():
    assert realised_vol([]) is None


# ---------------------------------------------------------------------------
# slippage_from_book
# ---------------------------------------------------------------------------


def test_slippage_buy_fits_in_best_level():
    book = parse_book(_RAW_BOOK)
    # buy 50 USD: fits entirely in best ask level (0.56, size=150) → avg = 0.56 = best_ask
    # slippage = |0.56 - 0.56| = 0
    assert slippage_from_book(book, size_usd=50, side="buy") == pytest.approx(0.0)


def test_slippage_buy_walks_two_levels():
    book = parse_book(_RAW_BOOK)
    # buy 200 USD: 150 at 0.56 + 50 at 0.57 → avg = (150*0.56 + 50*0.57) / 200 = 0.5625
    # best_ask = 0.56 → slippage = 0.0025
    assert slippage_from_book(book, size_usd=200, side="buy") == pytest.approx(0.0025, rel=1e-4)


def test_slippage_sell_side():
    book = parse_book(_RAW_BOOK)
    # sell 100 USD: fits in best bid (0.54, size=200) → avg = 0.54 = best_bid → slippage = 0
    assert slippage_from_book(book, size_usd=100, side="sell") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# parse_market clob_token_ids wired through (regression)
# ---------------------------------------------------------------------------


def test_parse_market_includes_clob_token_ids():
    """parse_market must forward clob_token_ids so the agent can call polymarket_orderbook."""
    from trader.core.clients.polymarket import parse_market

    token_ids = ["123456", "789012"]
    raw = {
        "id": "mkt1",
        "question": "Will it?",
        "slug": "will-it",
        "active": True,
        "closed": False,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.6", "0.4"]),
        "volume": "1000",
        "liquidity": "500",
        "endDate": "2026-12-01T00:00:00Z",
        "clobTokenIds": json.dumps(token_ids),
    }
    parsed = parse_market(raw, event_slug=None)
    assert parsed is not None
    assert parsed["clob_token_ids"] == token_ids


def test_parse_market_empty_clob_token_ids():
    from trader.core.clients.polymarket import parse_market

    raw = {
        "id": "mkt2", "question": "Q", "slug": "q",
        "active": True, "closed": False,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.5", "0.5"]),
        "volume": "0", "liquidity": "0", "endDate": "2026-12-01T00:00:00Z",
    }
    parsed = parse_market(raw, event_slug=None)
    assert parsed is not None
    assert parsed["clob_token_ids"] == []
