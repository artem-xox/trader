"""Gamma API request/response models and their processing.

All the quirks of Gamma's wire format are absorbed here, at the edge:
- `outcomes`, `outcomePrices`, `clobTokenIds` arrive as JSON-encoded strings;
- numerics (`volume`, `liquidity`, ...) arrive as strings;
- events nest markets, and one busy event can dominate a result list.

The client (`PolymarketClient`) only builds request params, validates responses into
these models, and serialises the compact summary/detail dicts the agent reasons over.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Cap markets taken from a single event so one busy event (e.g. an election with dozens
# of candidate markets, most at near-zero probability) cannot fill the whole result list.
PER_EVENT_CAP = 20


def _json_list(value: Any) -> list:
    """Gamma encodes list fields as JSON strings; tolerate both shapes."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    return value if isinstance(value, list) else []


def _tolerant_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class PublicSearchParams(BaseModel):
    """`GET /public-search` — Gamma's keyword index.

    `events_status="active"` is required: without it Gamma ranks resolved/old markets
    first and can bury (or omit) the active ones entirely — e.g. "nvidia" otherwise
    returns only closed markets and looks like "no markets". The `active`/`closed`
    params have no effect on this endpoint; `events_status` is the one that works.
    """

    q: str
    limit_per_type: int = Field(ge=1, le=20)
    events_status: str = "active"

    def as_params(self) -> dict[str, Any]:
        return self.model_dump()


class EventsParams(BaseModel):
    """`GET /events` — category browse (with `tag_slug`) or global trending (without).

    Lists active events highest-volume first; text filtering happens client-side
    because this endpoint has no keyword search.
    """

    tag_slug: str | None = None
    active: str = "true"
    closed: str = "false"
    limit: int = 50
    order: str = "volume"
    ascending: str = "false"

    def as_params(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class GammaMarket(BaseModel):
    """One market as Gamma returns it, normalised to Python types at validation."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    market_id: str | None = Field(default=None, alias="id")
    question: str | None = None
    slug: str | None = None
    description: str | None = None
    active: bool = True
    closed: bool = False
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float | None] = Field(default_factory=list, alias="outcomePrices")
    volume: float | None = None
    volume_24h: float | None = Field(default=None, alias="volume24hr")
    liquidity: float | None = None
    ends_at: str | None = Field(default=None, alias="endDate")
    clob_token_ids: list[str] = Field(default_factory=list, alias="clobTokenIds")

    @field_validator("outcomes", "clob_token_ids", mode="before")
    @classmethod
    def _decode_str_list(cls, v: Any) -> list[str]:
        return [str(i) for i in _json_list(v)]

    @field_validator("outcome_prices", mode="before")
    @classmethod
    def _decode_price_list(cls, v: Any) -> list[float | None]:
        return [_tolerant_float(p) for p in _json_list(v)]

    @field_validator("volume", "volume_24h", "liquidity", mode="before")
    @classmethod
    def _coerce_float(cls, v: Any) -> float | None:
        return _tolerant_float(v)

    def implied_probability(self) -> dict[str, float | None] | None:
        if self.outcomes and len(self.outcomes) == len(self.outcome_prices):
            return dict(zip(self.outcomes, self.outcome_prices))
        return None

    def url(self, event_slug: str | None = None) -> str | None:
        if event_slug:
            return f"https://polymarket.com/event/{event_slug}"
        return f"https://polymarket.com/market/{self.slug}" if self.slug else None

    def to_summary(self, event_slug: str | None = None) -> dict | None:
        """The compact shape the agent reasons over. None for closed/inactive markets —
        they are not actionable and would only pad the context."""
        if self.closed or not self.active:
            return None
        return {
            "market_id": self.market_id,
            "question": self.question,
            "url": self.url(event_slug),
            "implied_probability": self.implied_probability(),
            "volume": self.volume,
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "ends_at": self.ends_at,
            "clob_token_ids": self.clob_token_ids,
        }

    def to_detail(self, event_slug: str | None = None) -> dict:
        """Full detail incl. resolution criteria. Unlike `to_summary` this keeps
        closed/inactive markets — the user asked for this one specifically."""
        return {
            "market_id": self.market_id,
            "question": self.question,
            "description": self.description,
            "url": self.url(event_slug),
            "implied_probability": self.implied_probability(),
            "volume": self.volume,
            "liquidity": self.liquidity,
            "ends_at": self.ends_at,
            "closed": self.closed,
        }


class GammaEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str | None = None
    title: str | None = None
    markets: list[GammaMarket] = Field(default_factory=list)


class PublicSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    events: list[GammaEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def collect_markets(events: list[GammaEvent | dict], limit: int) -> list[dict]:
    """Flatten events into market summaries: at most `PER_EVENT_CAP` per event,
    at most `limit` total, in the order Gamma returned them. Accepts raw event dicts
    for convenience at the API boundary."""
    markets: list[dict] = []
    for event in events:
        if isinstance(event, dict):
            event = GammaEvent.model_validate(event)
        taken = 0
        for market in event.markets:
            summary = market.to_summary(event.slug)
            if summary:
                markets.append(summary)
                taken += 1
            if taken >= PER_EVENT_CAP or len(markets) >= limit:
                break
        if len(markets) >= limit:
            break
    return markets


def filter_events_by_query(events: list[GammaEvent], query: str) -> list[GammaEvent]:
    """Keep tag-browsed events whose title matches the query (Gamma's `/events` has no
    text search, so we filter client-side). Prefer events matching ALL query words; if
    none do, fall back to those matching any longer word — so a slightly-off phrasing
    still narrows."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3]
    if not tokens:
        return events
    titles = [(e, (e.title or "").lower()) for e in events]
    strict = [e for e, title in titles if all(t in title for t in tokens)]
    if strict:
        return strict
    long_tokens = [t for t in tokens if len(t) >= 4]
    return [e for e, title in titles if any(t in title for t in long_tokens)]


# Thin functional wrappers kept as the module's parsing API (used by tests and the
# CLOB regression suite); the logic lives on the models above.


def parse_market(raw: dict, event_slug: str | None) -> dict | None:
    return GammaMarket.model_validate(raw).to_summary(event_slug)


def parse_market_detail(raw: dict, event_slug: str | None = None) -> dict:
    return GammaMarket.model_validate(raw).to_detail(event_slug)
