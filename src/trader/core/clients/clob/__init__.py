"""Polymarket CLOB REST client — read-only price-formation data.

Covers the four public (no-auth) endpoints used for cost-aware analysis:
  /book            — full order book (bids + asks, string numerics)
  /midpoint        — market midpoint price
  /spread          — quoted bid-ask spread
  /prices-history  — time-series of trade/mid prices

All returned values are already normalised to Python types by the parse_* helpers.
Derived metrics (spread_bps, depth_within_2_ticks, realised_vol) are pure functions
over parsed data — no LLM, no side effects.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import httpx

CLOB_BASE_URL = "https://clob.polymarket.com"
_TIMEOUT = httpx.Timeout(15.0)


# ---------------------------------------------------------------------------
# Canonical parsed shapes
# ---------------------------------------------------------------------------


class BookLevel(NamedTuple):
    price: float
    size: float  # USD notional


class OrderBook(NamedTuple):
    market: str          # condition-id (0x...)
    asset_id: str        # token_id
    timestamp: str       # ISO-ish string from the exchange
    bids: list[BookLevel]  # sorted best-first (highest price first)
    asks: list[BookLevel]  # sorted best-first (lowest price first)
    tick_size: float
    min_order_size: float
    last_trade_price: float | None


# ---------------------------------------------------------------------------
# Raw-response parsers  (pure, no network)
# ---------------------------------------------------------------------------


def _float(v: str | float | int | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_book(raw: dict) -> OrderBook:
    """Convert a raw /book JSON dict into a typed OrderBook."""

    def _levels(raw_levels: list[dict]) -> list[BookLevel]:
        levels = []
        for lv in raw_levels:
            p = _float(lv.get("price"))
            s = _float(lv.get("size"))
            if p is not None and s is not None:
                levels.append(BookLevel(price=p, size=s))
        return levels

    bids = sorted(_levels(raw.get("bids", [])), key=lambda lv: lv.price, reverse=True)
    asks = sorted(_levels(raw.get("asks", [])), key=lambda lv: lv.price)

    return OrderBook(
        market=raw.get("market", ""),
        asset_id=raw.get("asset_id", ""),
        timestamp=raw.get("timestamp", ""),
        bids=bids,
        asks=asks,
        tick_size=float(raw.get("tick_size", 0.01)),
        min_order_size=float(raw.get("min_order_size", 5.0)),
        last_trade_price=_float(raw.get("last_trade_price")),
    )


def parse_history(raw: dict) -> list[tuple[int, float]]:
    """Convert a raw /prices-history JSON dict into [(unix_ts, price), ...]."""
    return [(int(p["t"]), float(p["p"])) for p in raw.get("history", []) if "t" in p and "p" in p]


# ---------------------------------------------------------------------------
# Derived metrics  (pure, no network)
# ---------------------------------------------------------------------------


def best_bid(book: OrderBook) -> float | None:
    return book.bids[0].price if book.bids else None


def best_ask(book: OrderBook) -> float | None:
    return book.asks[0].price if book.asks else None


def mid(book: OrderBook) -> float | None:
    b, a = best_bid(book), best_ask(book)
    return (b + a) / 2 if b is not None and a is not None else None


def spread_bps(book: OrderBook) -> float | None:
    """Quoted spread in basis points (×10 000 of mid)."""
    b, a, m = best_bid(book), best_ask(book), mid(book)
    if b is None or a is None or not m:
        return None
    return (a - b) / m * 10_000


def depth_within_2_ticks(book: OrderBook, side: str = "both") -> float:
    """Total USD depth within 2 ticks of the mid on the requested side.

    side: "bids" | "asks" | "both"
    """
    m = mid(book)
    if m is None:
        return 0.0
    tick = book.tick_size
    lo, hi = m - 2 * tick, m + 2 * tick

    def _sum(levels: list[BookLevel]) -> float:
        return sum(lv.size for lv in levels if lo <= lv.price <= hi)

    if side == "bids":
        return _sum(book.bids)
    if side == "asks":
        return _sum(book.asks)
    return _sum(book.bids) + _sum(book.asks)


def realised_vol(history: list[tuple[int, float]]) -> float | None:
    """Standard deviation of prices in the history series (population stdev)."""
    prices = [p for _, p in history]
    if len(prices) < 2:
        return None
    mean = sum(prices) / len(prices)
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    return math.sqrt(variance)


def slippage_from_book(book: OrderBook, size_usd: float, side: str = "buy") -> float:
    """Walk the book to estimate average fill price vs best touch, then compute slippage.

    Returns slippage as a fraction (e.g. 0.005 = 0.5 pp). Zero if the whole order fits
    at the best level or the book is empty/has no meaningful depth.

    side: "buy"  → walk asks (you're buying YES tokens)
         "sell" → walk bids (you're selling / buying NO tokens)
    """
    levels = book.asks if side == "buy" else book.bids
    if not levels:
        return 0.0
    best_touch = levels[0].price
    filled = 0.0
    cost = 0.0
    for lv in levels:
        take = min(lv.size, size_usd - filled)
        cost += take * lv.price
        filled += take
        if filled >= size_usd:
            break
    if filled == 0:
        return 0.0
    avg_price = cost / filled
    return abs(avg_price - best_touch)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class ClobClient:
    def __init__(
        self,
        base_url: str = CLOB_BASE_URL,
        timeout: httpx.Timeout = _TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def book(self, token_id: str) -> OrderBook:
        """Fetch and parse the full order book for a token."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/book", params={"token_id": token_id})
            resp.raise_for_status()
        return parse_book(resp.json())

    async def midpoint(self, token_id: str) -> float | None:
        """Fetch the midpoint price for a token."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/midpoint", params={"token_id": token_id})
            resp.raise_for_status()
        return _float(resp.json().get("mid"))

    async def spread(self, token_id: str) -> float | None:
        """Fetch the quoted spread for a token."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/spread", params={"token_id": token_id})
            resp.raise_for_status()
        return _float(resp.json().get("spread"))

    async def prices_history(
        self,
        token_id: str,
        interval: str = "1d",
        fidelity: int = 60,
    ) -> list[tuple[int, float]]:
        """Fetch price history. interval: 1m | 1h | 1d | 1w | 1mo | max."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/prices-history",
                params={"market": token_id, "interval": interval, "fidelity": fidelity},
            )
            resp.raise_for_status()
        return parse_history(resp.json())

    async def orderbook_snapshot(self, token_id: str) -> dict:
        """Fetch all CLOB data for a token and return a compact summary dict.

        This is the shape passed to the agent tool. Pure data, no LLM.
        """
        try:
            book = await self.book(token_id)
        except httpx.HTTPError as exc:
            return {"error": f"CLOB book fetch failed: {exc}"}

        history_1h = []
        history_24h = []
        try:
            history_1h = await self.prices_history(token_id, interval="1h", fidelity=60)
            history_24h = await self.prices_history(token_id, interval="1d", fidelity=60)
        except httpx.HTTPError:
            pass  # history is best-effort; book data is still useful

        m = mid(book)
        sp_bps = spread_bps(book)
        depth_2t = depth_within_2_ticks(book)
        vol_1h = realised_vol(history_1h)
        vol_24h = realised_vol(history_24h)

        return {
            "token_id": token_id,
            "market": book.market,
            "timestamp": book.timestamp,
            "best_bid": best_bid(book),
            "best_ask": best_ask(book),
            "mid": round(m, 6) if m is not None else None,
            "spread_bps": round(sp_bps, 2) if sp_bps is not None else None,
            "depth_within_2_ticks_usd": round(depth_2t, 2),
            "tick_size": book.tick_size,
            "min_order_size_usd": book.min_order_size,
            "last_trade_price": book.last_trade_price,
            "realised_vol_1h": round(vol_1h, 6) if vol_1h is not None else None,
            "realised_vol_24h": round(vol_24h, 6) if vol_24h is not None else None,
            "bids_top5": [{"price": lv.price, "size": lv.size} for lv in book.bids[:5]],
            "asks_top5": [{"price": lv.price, "size": lv.size} for lv in book.asks[:5]],
        }
