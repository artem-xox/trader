"""Request/response models for the agent HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from trader.core.models.domain import ResearchResult


class InvokeRequest(BaseModel):
    message: str = Field(..., description="User message / topic to research")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; scopes per-chat memory"
    )


class InvokeResponse(BaseModel):
    response: str = Field(description="Human-readable markdown answer")
    result: ResearchResult = Field(description="Structured research result")
