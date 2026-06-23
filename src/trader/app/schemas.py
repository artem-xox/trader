"""Request/response models for the agent HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field, SerializeAsAny

from trader.core.models.domain import SkillResult


class InvokeRequest(BaseModel):
    message: str = Field(..., description="User message / topic to research")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; scopes per-chat memory"
    )


class InvokeResponse(BaseModel):
    response: str = Field(description="Human-readable markdown answer")
    # Any SkillResult subtype (GeneralAnswer / ResearchResult / MarketAnalysis).
    # SerializeAsAny keeps the concrete subclass fields instead of narrowing to the base.
    result: SerializeAsAny[SkillResult] = Field(description="Structured result")
