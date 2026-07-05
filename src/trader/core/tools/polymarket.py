"""Polymarket data tools — the domain-specific half of the toolset.

- `search`: active markets via the public Gamma API (no auth).
- `market`: full detail for one market via the Gamma API.
- `orderbook`: live CLOB snapshot — spread, depth, price history (no auth).
- `tradability`: hard filters + composite tradability score over the live book.

All return JSON strings so the model reasons over a consistent, compact shape. Prices
are normalized to implied probabilities. The tools close over injected clients — they
are built in the composition root (`trader.core.bootstrap`), not at import time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from langchain_core.tools import BaseTool, tool

from trader.core.clients import ClobClient, PolymarketClient
from trader.core.tools.schemas import (
    OrderbookInput,
    PolymarketMarketInput,
    PolymarketSearchInput,
    TradabilityInput,
)
from trader.core.trading import tradability


def _book_age_s(timestamp: str) -> float | None:
    """Age of a CLOB book snapshot in seconds. CLOB returns a ms-epoch string; be
    tolerant of ISO 8601 too. None when unparseable (age filter then doesn't apply)."""
    now = datetime.now(timezone.utc)
    try:
        return now.timestamp() - int(timestamp) / 1000.0
    except (TypeError, ValueError):
        pass
    try:
        then = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return (now - then).total_seconds()
    except (TypeError, ValueError):
        return None


def _days_until(ends_at: str | None) -> float | None:
    if not ends_at:
        return None
    try:
        end = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return (end - datetime.now(timezone.utc)).total_seconds() / 86_400.0


@dataclass(frozen=True)
class PolymarketTools:
    """The Polymarket toolset with named access, so wiring code never unpacks by
    position."""

    search: BaseTool
    market: BaseTool
    orderbook: BaseTool
    tradability: BaseTool

    def as_list(self) -> list[BaseTool]:
        return [self.search, self.market, self.orderbook, self.tradability]


def build_polymarket_tools(
    polymarket: PolymarketClient,
    clob: ClobClient | None = None,
) -> PolymarketTools:
    _clob = clob or ClobClient()

    @tool(args_schema=PolymarketSearchInput)
    async def polymarket_search(query: str = "", limit: int = 8, tag: str | None = None) -> str:
        """Search active Polymarket prediction markets matching a topic or keyword.

        Markets are indexed in English, so search with short English keywords for the most
        distinctive entity (a name, e.g. "Jesus", "Bitcoin"), not a long literal phrase or a
        non-English one. If a query returns nothing relevant, reformulate and try again.

        With an EMPTY query it browses the highest-volume active markets (trending) across
        all categories — use this for abstract asks ("most promising", "undervalued",
        "what's hot") where no single keyword captures the intent, then narrow with
        follow-up keyword searches on the themes you see.

        For individual sports events — a specific Formula 1 race or qualifying, or a single
        football (soccer) match — set `tag` to the category ('f1' or 'soccer') and use the
        event name as the query (e.g. query="Austrian Grand Prix", tag="f1"). The general
        keyword index does NOT surface these per-event sports markets; a tagged search does.

        Returns a JSON list of markets with their question, current implied probabilities
        per outcome, traded volume (total and 24h), liquidity, end date, `clob_token_ids`,
        and a link. At most 3 markets per event are returned, so results span distinct
        events. Use this to find real markets before suggesting any bet — never invent
        markets.
        """
        return await polymarket.search(query, limit=limit, tag=tag)

    @tool(args_schema=PolymarketMarketInput)
    async def polymarket_market(slug: str) -> str:
        """Fetch full detail for a specific Polymarket market by its slug.

        The slug is the last path segment of a polymarket.com URL. Returns a JSON list of
        the market(s) at that slug with question, resolution criteria (`description`),
        current implied probabilities, volume, liquidity, end date, and closed flag. Use
        this to analyze a single market the user pointed to.
        """
        return await polymarket.market(slug)

    @tool(args_schema=OrderbookInput)
    async def polymarket_orderbook(token_id: str) -> str:
        """Fetch live CLOB order-book data for a Polymarket token.

        Returns a JSON object with: best_bid, best_ask, mid, spread_bps,
        depth_within_2_ticks_usd (USD depth within 2 ticks of mid on both sides),
        realised_vol_1h and realised_vol_24h (price standard deviation), last_trade_price,
        tick_size, min_order_size_usd, and the top-5 bid/ask levels.

        The token_id is the first element of `clob_token_ids` from the market data
        (use polymarket_search or polymarket_market to get it first). For binary markets
        there are two tokens — YES (index 0) and NO (index 1); use the YES token_id to get
        the YES side book; the NO side is implicit (NO price ≈ 1 − YES price).

        Use this to assess execution cost before recommending a trade: a wide spread_bps
        or thin depth_within_2_ticks_usd means the edge may not survive after fees and
        slippage.
        """
        snapshot = await _clob.orderbook_snapshot(token_id)
        return json.dumps(snapshot)

    @tool(args_schema=TradabilityInput)
    async def polymarket_tradability(
        token_id: str,
        market_id: str | None = None,
        fair_probability: float | None = None,
        ends_at: str | None = None,
        volume_24h_usd: float | None = None,
    ) -> str:
        """Score how tradable a Polymarket market actually is, from its live order book.

        Call this for EVERY candidate you consider suggesting (use the YES token — first
        element of `clob_token_ids`), after you have formed a fair-probability estimate
        from evidence. Pass the market's `market_id` too — it is echoed back so the
        verdict stays attached to the right market. Pass `ends_at` and `volume_24h` from
        the market data when you have them — each enables one more component of the score.

        Returns JSON:
        - `tradable` + `reject_reasons`: hard-filter verdict. A market with
          spread_too_wide / depth_too_thin / extreme_price / stale_book / no_orderbook
          must NOT be suggested — mention notable rejects briefly in the summary instead.
        - `find_score` (0-1): composite tradability+edge rank — higher is better; use it
          to order the shortlist.
        - `subscores`: liquidity / edge / volatility / information / horizon components.
        - `net_edge`: your edge minus half the spread, in probability points.
        - `spread_bps`, `depth_usd`, `mid`, `maker_or_taker`: copy these into the
          suggestion fields verbatim — never estimate them yourself.
        """
        snapshot = await _clob.orderbook_snapshot(token_id)
        if "error" in snapshot:
            return json.dumps(
                {
                    "market_id": market_id,
                    "tradable": False,
                    "reject_reasons": ["no_orderbook"],
                    "error": snapshot["error"],
                }
            )
        verdict = tradability(
            mid=snapshot["mid"],
            spread_bps=snapshot["spread_bps"],
            depth_usd=snapshot["depth_within_2_ticks_usd"],
            book_age_s=_book_age_s(snapshot["timestamp"]),
            realised_vol_24h=snapshot["realised_vol_24h"],
            volume_24h_usd=volume_24h_usd,
            fair_probability=fair_probability,
            days_to_resolution=_days_until(ends_at),
        )
        return json.dumps(
            {
                "market_id": market_id,
                "token_id": token_id,
                **verdict,
                "spread_bps": snapshot["spread_bps"],
                "depth_usd": snapshot["depth_within_2_ticks_usd"],
                "mid": snapshot["mid"],
            }
        )

    return PolymarketTools(
        search=polymarket_search,
        market=polymarket_market,
        orderbook=polymarket_orderbook,
        tradability=polymarket_tradability,
    )
