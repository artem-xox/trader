"""Domain output models — the contract the agent produces for the user.

These are the structured result of a research run: a short summary plus a ranked list
of market suggestions, each with an explicit risk assessment. The planner reasons in
free text during the loop; the `Responder` step coerces the conclusion into this shape
so callers (HTTP, Telegram, evals) consume structure instead of prose.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Level(StrEnum):
    """Shared low/medium/high scale for confidence and risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskAssessment(BaseModel):
    level: Level = Field(description="Overall risk of taking this bet.")
    factors: list[str] = Field(
        default_factory=list,
        description="Key risk factors (e.g. low liquidity, far resolution, ambiguous criteria).",
    )
    note: str = Field(description="One-line risk summary.")


class Suggestion(BaseModel):
    market_id: str = Field(description="Polymarket market id, exactly as returned by the tools.")
    question: str = Field(description="The market question.")
    url: str | None = Field(default=None, description="Link to the market on Polymarket.")
    implied_probability: float | None = Field(
        default=None,
        description="The implied probability (0-1) the analysis keys on.",
    )
    rationale: str = Field(description="Why this bet is interesting — the edge, in one or two lines.")
    confidence: Level = Field(description="Confidence in the rationale.")
    risk: RiskAssessment


class ResearchResult(BaseModel):
    """The agent's final answer for one research turn."""

    summary: str = Field(description="Short natural-language summary for the user.")
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="Ranked shortlist of suggested markets; empty if nothing worth suggesting.",
    )
