"""Request/response models for the agent HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InvokeRequest(BaseModel):
    message: str = Field(..., description="User message / topic to research")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id (reserved for memory)"
    )


class InvokeResponse(BaseModel):
    response: str
