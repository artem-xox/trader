"""Pydantic input schemas for agent tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolymarketSearchInput(BaseModel):
    query: str = Field(
        description="Topic or keyword to search active Polymarket prediction markets for.",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of markets to return.",
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
