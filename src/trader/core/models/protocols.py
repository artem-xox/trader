"""Structural interfaces for the agent core.

These Protocols define the contracts the rest of the system depends on, so concrete
implementations (components, agents) can be swapped without touching callers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from trader.core.models.domain import SkillResult
from trader.core.models.streaming import ProgressEvent
from trader.core.models.schemas import (
    AgentState,
    ExecutorResponse,
    GuardResponse,
    Messages,
    PlannerResponse,
    ResponderResponse,
    SelectorResponse,
    VerifierResponse,
)


@runtime_checkable
class Selector(Protocol):
    """First node: picks at most one skill for the turn (or normal mode)."""

    async def __call__(self, state: AgentState) -> SelectorResponse: ...


@runtime_checkable
class Planner(Protocol):
    """ReAct "reason" step: calls the LLM and appends its reply to the conversation."""

    async def __call__(self, state: AgentState) -> PlannerResponse: ...


@runtime_checkable
class Guard(Protocol):
    """Safety gate before tool execution."""

    async def __call__(self, state: AgentState) -> GuardResponse: ...


@runtime_checkable
class Executor(Protocol):
    """ReAct "act" step: runs tool calls and appends ToolMessages."""

    async def __call__(self, state: AgentState) -> ExecutorResponse: ...


@runtime_checkable
class Responder(Protocol):
    """Synthesizes the loop's conclusion into the structured `ResearchResult`."""

    async def __call__(self, state: AgentState) -> ResponderResponse: ...


@runtime_checkable
class Verifier(Protocol):
    """Final gate before the answer leaves the loop."""

    async def __call__(self, state: AgentState) -> VerifierResponse: ...


@runtime_checkable
class Agent(Protocol):
    """An agent runs a turn for a thread and returns the structured result.

    Conversation history is owned by the graph checkpointer (keyed by `thread_id`); the
    caller passes only the new message(s).
    """

    async def invoke(self, messages: Messages, *, thread_id: str | None = None) -> SkillResult: ...

    def astream(
        self, messages: Messages, *, thread_id: str | None = None
    ) -> AsyncIterator[ProgressEvent]:
        """Run a turn and yield progress events, ending with the terminal `final` event."""
        ...
