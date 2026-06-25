"""Live tests for the CLOB client — hit real CLOB REST endpoints.

Marked `live` so they are excluded from offline CI runs (make test).
Run with: make test-live  or  pytest -m live tests/unit/test_clob_client_live.py
"""

from __future__ import annotations

import pytest

from trader.core.clients.clob import ClobClient, mid, spread_bps

# A consistently liquid market (LeBron Lakers 2026-27)
_TOKEN_ID = "87597959855794011322089941773286459303887751541485563842443201472132453340025"


@pytest.mark.live
@pytest.mark.asyncio
async def test_book_returns_sane_values():
    client = ClobClient()
    book = await client.book(_TOKEN_ID)
    assert book.bids, "bids must not be empty for a liquid market"
    assert book.asks, "asks must not be empty for a liquid market"
    m = mid(book)
    assert m is not None
    assert 0.0 < m < 1.0, f"mid out of [0,1]: {m}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_midpoint_matches_book_mid():
    client = ClobClient()
    book = await client.book(_TOKEN_ID)
    endpoint_mid = await client.midpoint(_TOKEN_ID)
    book_mid = mid(book)
    assert endpoint_mid is not None
    assert book_mid is not None
    # Should be very close; allow 1 tick of drift between the two fetches
    assert abs(endpoint_mid - book_mid) <= book.tick_size * 2


@pytest.mark.live
@pytest.mark.asyncio
async def test_spread_bps_positive():
    client = ClobClient()
    book = await client.book(_TOKEN_ID)
    sp = spread_bps(book)
    assert sp is not None
    assert sp >= 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_prices_history_nonempty():
    client = ClobClient()
    history = await client.prices_history(_TOKEN_ID, interval="1d", fidelity=60)
    assert len(history) >= 1
    assert all(isinstance(t, int) and isinstance(p, float) for t, p in history)
    assert all(0.0 <= p <= 1.0 for _, p in history)


@pytest.mark.live
@pytest.mark.asyncio
async def test_orderbook_snapshot_shape():
    client = ClobClient()
    snap = await client.orderbook_snapshot(_TOKEN_ID)
    assert "error" not in snap, snap.get("error")
    required = {"token_id", "best_bid", "best_ask", "mid", "spread_bps",
                "depth_within_2_ticks_usd", "realised_vol_1h", "realised_vol_24h",
                "bids_top5", "asks_top5"}
    assert required.issubset(snap.keys())
    assert 0.0 < snap["mid"] < 1.0
    assert snap["spread_bps"] >= 0
