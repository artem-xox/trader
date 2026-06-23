"""Domain output models — the structured contract the agent produces for the user.

The planner reasons in free text during the loop; the `Responder` step coerces the
conclusion into one of these shapes so callers (HTTP, Telegram, evals) consume structure
instead of prose. The active skill decides which schema the responder targets:
`ResearchResult` for the `find` skill, `GeneralAnswer` in normal mode.

Every result carries a `summary` (the `SkillResult` base), so the loop can always emit a
human-readable assistant message regardless of which schema was used.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SkillResult(BaseModel):
    """Base for every responder output — guarantees a human-readable summary."""

    summary: str = Field(description="Short natural-language answer for the user.")

    def referenced_market_ids(self) -> list[str]:
        """Market ids this result asserts. The verifier checks each one exists in tool
        output (anti-hallucination). Schemas with no markets return nothing."""
        return []


class GeneralAnswer(SkillResult):
    """Normal-mode answer: just the summary, no domain structure."""


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


class ResearchResult(SkillResult):
    """The `find` skill's answer for one research turn."""

    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description="Ranked shortlist of suggested markets; empty if nothing worth suggesting.",
    )

    def referenced_market_ids(self) -> list[str]:
        return [s.market_id for s in self.suggestions]


class Stance(StrEnum):
    """The analyst's directional call on a single market."""

    LEAN_YES = "lean_yes"
    LEAN_NO = "lean_no"
    PASS = "pass"


class MarketAnalysis(SkillResult):
    """The `analyze` skill's answer: a deep dive on one market with a risk model."""

    market_id: str = Field(description="Polymarket market id, exactly as returned by the tools.")
    question: str = Field(description="The market question.")
    url: str | None = Field(default=None, description="Link to the market on Polymarket.")
    resolution_criteria: str | None = Field(
        default=None, description="How the market resolves, from its description."
    )
    implied_probability: float | None = Field(
        default=None, description="The market's current implied probability (0-1)."
    )
    fair_probability: float | None = Field(
        default=None, description="The analyst's own estimate of the true probability (0-1)."
    )
    edge: str = Field(description="Where the analyst's view diverges from the market, and why.")
    stance: Stance = Field(description="Directional call.")
    confidence: Level = Field(description="Confidence in the analysis.")
    key_factors: list[str] = Field(
        default_factory=list, description="The main drivers behind the call."
    )
    risk: RiskAssessment

    def referenced_market_ids(self) -> list[str]:
        return [self.market_id]
