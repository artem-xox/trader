"""Structural interfaces for the agent core.

These Protocols define the contracts the rest of the system depends on, so concrete
implementations (components, agents) can be swapped without touching callers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from trader.core.models.schemas import (
    AgentState,
    ExecutorResponse,
    GuardResponse,
    Messages,
    PlannerResponse,
    VerifierResponse,
)


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
class Verifier(Protocol):
    """Final gate before the answer leaves the loop."""

    async def __call__(self, state: AgentState) -> VerifierResponse: ...


@runtime_checkable
class Agent(Protocol):
    """An agent runs a conversation (full history passed in) and returns an answer."""

    async def invoke(self, messages: Messages) -> str: ...
