"""Tradability scoring for the `find` skill — pure functions, no network, no LLM.

Turns one market's CLOB/Gamma metrics into:
- hard-filter verdict (`tradable` + `reject_reasons`) — applied BEFORE scoring, so
  loud-but-untradeable markets are dropped with an explanation instead of ranked;
- a composite find score `S = 0.30·L + 0.25·E + 0.15·V + 0.20·I + 0.10·T`
  (liquidity quality, net edge after cost, realised volatility, information-flow
  intensity, time-to-resolution fit). Missing components are skipped and the
  remaining weights renormalised, so a market without e.g. a fair-probability
  estimate still gets a comparable 0..1 score;
- a maker/taker execution preference.

All thresholds are heuristics for read-only research ranking, not execution params.
"""

from __future__ import annotations

# Hard filters — a market failing any of these is not worth ranking at all.
MAX_SPREAD_BPS = 600.0  # wider than 6% of mid: edge rarely survives the crossing cost
MIN_DEPTH_USD = 500.0  # less than this within 2 ticks of mid: too thin to fill
MAX_BOOK_AGE_S = 300.0  # book snapshot older than 5 min: stale, do not trust
MIN_MID, MAX_MID = 0.02, 0.98  # dead longshots/locks: payoff asymmetry eats the edge

# Subscore saturation points (value at which a component scores 1.0).
FULL_DEPTH_USD = 5_000.0
FULL_NET_EDGE = 0.10  # 10 pp of net edge after half-spread = full edge score
FULL_REALISED_VOL = 0.05  # 5 pp daily price stdev = full volatility score
FULL_VOLUME_24H_USD = 20_000.0

# Composite weights (PLAN.md Phase 2). Renormalised over available components.
WEIGHTS = {
    "liquidity": 0.30,
    "edge": 0.25,
    "volatility": 0.15,
    "information": 0.20,
    "horizon": 0.10,
}

TAKER_MAX_SPREAD_BPS = 100.0  # tighter than this, crossing the spread is fine


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _liquidity_score(spread_bps: float, depth_usd: float) -> float:
    spread_part = _clamp01(1.0 - spread_bps / MAX_SPREAD_BPS)
    depth_part = _clamp01(depth_usd / FULL_DEPTH_USD)
    return 0.5 * spread_part + 0.5 * depth_part


def _edge_score(mid: float, spread_bps: float, fair_probability: float) -> tuple[float, float]:
    """Net edge after paying half the spread, as (score, net_edge in probability points)."""
    half_spread = (spread_bps / 10_000.0) * mid / 2.0
    net_edge = max(0.0, abs(fair_probability - mid) - half_spread)
    return _clamp01(net_edge / FULL_NET_EDGE), net_edge


def _horizon_score(days_to_resolution: float) -> float:
    """Time-to-resolution fit: capital locked for months or a market resolving in hours
    both rank worse than the 3–60 day sweet spot."""
    d = days_to_resolution
    if d <= 0.5:
        return 0.0
    if d < 3.0:
        return (d - 0.5) / 2.5
    if d <= 60.0:
        return 1.0
    if d >= 240.0:
        return 0.0
    return (240.0 - d) / 180.0


def tradability(
    *,
    mid: float | None,
    spread_bps: float | None,
    depth_usd: float,
    book_age_s: float | None = None,
    realised_vol_24h: float | None = None,
    volume_24h_usd: float | None = None,
    fair_probability: float | None = None,
    days_to_resolution: float | None = None,
) -> dict:
    """Score one market's tradability. Returns a JSON-ready dict:

    {tradable, reject_reasons, find_score, subscores, net_edge, maker_or_taker}

    `find_score` is None when the market fails a hard filter (it should be dropped,
    not ranked). Subscores that lack their input are None and excluded from the
    weighted score.
    """
    reasons: list[str] = []
    if mid is None or spread_bps is None:
        reasons.append("no_orderbook")
    else:
        if spread_bps > MAX_SPREAD_BPS:
            reasons.append("spread_too_wide")
        if not MIN_MID <= mid <= MAX_MID:
            reasons.append("extreme_price")
    if depth_usd < MIN_DEPTH_USD:
        reasons.append("depth_too_thin")
    if book_age_s is not None and book_age_s > MAX_BOOK_AGE_S:
        reasons.append("stale_book")

    if reasons:
        return {
            "tradable": False,
            "reject_reasons": reasons,
            "find_score": None,
            "subscores": None,
            "net_edge": None,
            "maker_or_taker": None,
        }

    assert mid is not None and spread_bps is not None  # narrowed by the no_orderbook check

    net_edge: float | None = None
    edge: float | None = None
    if fair_probability is not None:
        edge, net_edge = _edge_score(mid, spread_bps, fair_probability)

    subscores: dict[str, float | None] = {
        "liquidity": _liquidity_score(spread_bps, depth_usd),
        "edge": edge,
        "volatility": (
            _clamp01(realised_vol_24h / FULL_REALISED_VOL)
            if realised_vol_24h is not None
            else None
        ),
        "information": (
            _clamp01(volume_24h_usd / FULL_VOLUME_24H_USD)
            if volume_24h_usd is not None
            else None
        ),
        "horizon": (
            _horizon_score(days_to_resolution) if days_to_resolution is not None else None
        ),
    }

    available = {k: v for k, v in subscores.items() if v is not None}
    total_weight = sum(WEIGHTS[k] for k in available)
    score = sum(WEIGHTS[k] * v for k, v in available.items()) / total_weight

    return {
        "tradable": True,
        "reject_reasons": [],
        "find_score": round(score, 4),
        "subscores": {k: (round(v, 4) if v is not None else None) for k, v in subscores.items()},
        "net_edge": round(net_edge, 4) if net_edge is not None else None,
        "maker_or_taker": "taker" if spread_bps <= TAKER_MAX_SPREAD_BPS else "maker",
    }
