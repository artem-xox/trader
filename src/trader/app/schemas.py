"""Request/response models for the agent HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, SerializeAsAny

from trader.core.models.domain import SkillResult


class InvokeRequest(BaseModel):
    message: str = Field(..., description="User message / topic to research")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; scopes per-chat memory"
    )
    debug: bool = Field(
        default=False,
        description="When true, capture the LangSmith trace URL for this turn (if tracing is on)",
    )


class InvokeResponse(BaseModel):
    response: str = Field(description="Human-readable markdown answer")
    # Any SkillResult subtype (GeneralAnswer / ResearchResult / MarketAnalysis).
    # SerializeAsAny keeps the concrete subclass fields instead of narrowing to the base.
    result: SerializeAsAny[SkillResult] = Field(description="Structured result")
    trace_url: str | None = Field(
        default=None, description="LangSmith trace URL for this turn (debug mode only)"
    )


class StreamEvent(BaseModel):
    """One server-sent event from `POST /agent/stream`.

    `status` events drive a live progress indicator; the terminal `final` event carries the
    same payload as `InvokeResponse`; `error` signals the run failed mid-stream.
    """

    kind: Literal["status", "final", "error"]
    label: str = Field(default="", description="Semantic status key, e.g. 'tool:web_search'")
    detail: str | None = Field(default=None, description="Short hint for the step (a query/slug)")
    response: str | None = Field(default=None, description="Human-readable markdown answer (final)")
    result: SerializeAsAny[SkillResult] | None = Field(default=None, description="Structured result")
    trace_url: str | None = Field(default=None, description="LangSmith trace URL (final, debug mode)")


# ---------------------------------------------------------------------------
# Web client: conversations and their transcripts (docs/WEB.md §5.1)
# ---------------------------------------------------------------------------


class Conversation(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class Message(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str = Field(description="User text, or the assistant's markdown answer")
    # Stored as jsonb and returned as-is: the browser renders market cards from it, and
    # re-validating into a SkillResult subtype here would buy nothing.
    result: dict[str, Any] | None = Field(default=None, description="Structured result")
    trace_url: str | None = None
    created_at: datetime


class ConversationDetail(Conversation):
    messages: list[Message] = Field(default_factory=list)


class TitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TurnRequest(BaseModel):
    message: str = Field(..., min_length=1, description="What the user typed")
    debug: bool = Field(default=False, description="Attach a LangSmith trace URL to the answer")
