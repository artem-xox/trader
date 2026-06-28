"""Request/response models for the agent HTTP API."""

from __future__ import annotations

from typing import Literal

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
