"""Pydantic input schemas for agent tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolymarketSearchInput(BaseModel):
    query: str = Field(
        description="Topic or keyword to search active Polymarket prediction markets for. "
        "With `tag` set, use the distinctive event name (e.g. 'Austrian Grand Prix', "
        "'Algeria vs Austria').",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of markets to return.",
    )
    tag: str | None = Field(
        default=None,
        description="Optional category to scope the search to. Required for individual "
        "sports events (a single F1 race/qualifying, one football match), which the keyword "
        "index does not surface. Supported: 'f1' (Formula 1) and 'soccer' (football: World "
        "Cup, leagues, single fixtures). Leave unset for general topics.",
    )


class PolymarketMarketInput(BaseModel):
    slug: str = Field(
        description="Market or event slug — the last path segment of a polymarket.com URL.",
    )


class WebSearchInput(BaseModel):
    query: str = Field(
        description="Search query for current news, facts, and context on a topic.",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of web results to return.",
    )


class CalculatorInput(BaseModel):
    expression: str = Field(
        description="Arithmetic expression to evaluate, e.g. '0.62 * (1/0.55 - 1) - 0.38'. "
        "Supports + - * / // % **, parentheses, and sqrt/log/ln/log10/exp/abs/round/min/max, "
        "and the constants pi and e.",
    )


class WebFetchInput(BaseModel):
    url: str = Field(
        description="Full URL of a web page to read in detail.",
    )


class OrderbookInput(BaseModel):
    token_id: str = Field(
        description="CLOB token id for the YES or NO side of a Polymarket market. "
        "Available as the first element of `clob_token_ids` in the market data.",
    )


class ThinkInput(BaseModel):
    thought: str = Field(
        description="Your private reasoning: what the evidence implies, a step-by-step "
        "analysis, a probability estimate with its justification, or a plan for next steps.",
    )
