"""Offline tests for the tradability scoring module — pure functions, no network."""

from __future__ import annotations

import pytest

from trader.core.trading import (
    MAX_SPREAD_BPS,
    MIN_DEPTH_USD,
    WEIGHTS,
    tradability,
)

# A healthy, liquid market: tight spread, deep book, fresh snapshot.
_HEALTHY = dict(
    mid=0.55,
    spread_bps=80.0,
    depth_usd=6_000.0,
    book_age_s=5.0,
    realised_vol_24h=0.03,
    volume_24h_usd=15_000.0,
    fair_probability=0.62,
    days_to_resolution=30.0,
)


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------


def test_healthy_market_is_tradable():
    verdict = tradability(**_HEALTHY)
    assert verdict["tradable"] is True
    assert verdict["reject_reasons"] == []
    assert 0.0 <= verdict["find_score"] <= 1.0


def test_wide_spread_rejected():
    verdict = tradability(**{**_HEALTHY, "spread_bps": MAX_SPREAD_BPS + 1})
    assert verdict["tradable"] is False
    assert "spread_too_wide" in verdict["reject_reasons"]
    assert verdict["find_score"] is None


def test_thin_depth_rejected():
    verdict = tradability(**{**_HEALTHY, "depth_usd": MIN_DEPTH_USD - 1})
    assert verdict["tradable"] is False
    assert "depth_too_thin" in verdict["reject_reasons"]


def test_extreme_longshot_rejected():
    verdict = tradability(**{**_HEALTHY, "mid": 0.01, "fair_probability": 0.03})
    assert verdict["tradable"] is False
    assert "extreme_price" in verdict["reject_reasons"]


def test_extreme_lock_rejected():
    verdict = tradability(**{**_HEALTHY, "mid": 0.99, "fair_probability": 0.995})
    assert "extreme_price" in verdict["reject_reasons"]


def test_stale_book_rejected():
    verdict = tradability(**{**_HEALTHY, "book_age_s": 3600.0})
    assert verdict["tradable"] is False
    assert "stale_book" in verdict["reject_reasons"]


def test_missing_book_rejected():
    verdict = tradability(mid=None, spread_bps=None, depth_usd=0.0)
    assert verdict["tradable"] is False
    assert "no_orderbook" in verdict["reject_reasons"]


def test_multiple_reasons_accumulate():
    verdict = tradability(
        **{**_HEALTHY, "spread_bps": 1_000.0, "depth_usd": 10.0, "book_age_s": 900.0}
    )
    assert set(verdict["reject_reasons"]) == {"spread_too_wide", "depth_too_thin", "stale_book"}


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def test_all_components_present_uses_full_weights():
    verdict = tradability(**_HEALTHY)
    sub = verdict["subscores"]
    assert all(v is not None for v in sub.values())
    expected = sum(WEIGHTS[k] * sub[k] for k in WEIGHTS)
    assert verdict["find_score"] == pytest.approx(expected, abs=1e-3)


def test_missing_components_renormalise():
    """Without fair_probability / volume / vol / horizon the score is liquidity-only —
    still on the same 0..1 scale, not scaled down by the missing weights."""
    verdict = tradability(
        mid=0.55, spread_bps=80.0, depth_usd=6_000.0, book_age_s=5.0
    )
    sub = verdict["subscores"]
    assert sub["edge"] is None and sub["information"] is None
    assert verdict["find_score"] == pytest.approx(sub["liquidity"], abs=1e-3)


def test_better_liquidity_scores_higher():
    tight = tradability(**_HEALTHY)
    wide = tradability(**{**_HEALTHY, "spread_bps": 400.0, "depth_usd": 800.0})
    assert tight["find_score"] > wide["find_score"]


def test_net_edge_subtracts_half_spread():
    verdict = tradability(**_HEALTHY)
    # |0.62 - 0.55| = 0.07 gross; half-spread = 80/10000 * 0.55 / 2 = 0.0022
    assert verdict["net_edge"] == pytest.approx(0.07 - 0.0022, abs=1e-4)


def test_edge_dies_after_spread():
    """A narratively-attractive edge that the spread fully consumes scores zero."""
    verdict = tradability(
        **{**_HEALTHY, "spread_bps": 500.0, "fair_probability": 0.56}
    )
    # gross edge 0.01 < half-spread 0.0138 → net 0
    assert verdict["net_edge"] == 0.0
    assert verdict["subscores"]["edge"] == 0.0


# ---------------------------------------------------------------------------
# Horizon fit & maker/taker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0.1, 0.0), (3.0, 1.0), (30.0, 1.0), (60.0, 1.0), (240.0, 0.0), (400.0, 0.0)],
)
def test_horizon_sweet_spot(days: float, expected: float):
    verdict = tradability(**{**_HEALTHY, "days_to_resolution": days})
    assert verdict["subscores"]["horizon"] == pytest.approx(expected)


def test_horizon_tapers_between_anchors():
    near = tradability(**{**_HEALTHY, "days_to_resolution": 90.0})
    far = tradability(**{**_HEALTHY, "days_to_resolution": 180.0})
    assert 0.0 < far["subscores"]["horizon"] < near["subscores"]["horizon"] < 1.0


def test_tight_spread_prefers_taker():
    assert tradability(**_HEALTHY)["maker_or_taker"] == "taker"


def test_wide_spread_prefers_maker():
    verdict = tradability(**{**_HEALTHY, "spread_bps": 300.0})
    assert verdict["maker_or_taker"] == "maker"
