"""Data schemas shared across the agent core: graph state and verdict types."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph.message import add_messages

# The conversation passed in/out of the agent. History is owned by the UI layer and
# handed to the agent at invocation time.
Messages = list[AnyMessage]

class PlannerAction(StrEnum):
    """Planner decides whether to act or answer."""

    ACT = "act"
    ANSWER = "answer"


class GuardVerdict(StrEnum):
    """Guard gates tool execution: are the proposed tool calls safe/adequate to run?"""

    ALLOW = "allow"
    BLOCK = "block"


class ReviewVerdict(StrEnum):
    """Verifier gates the final answer before it leaves the loop."""

    OK = "ok"
    REVISE = "revise"


class AgentState(TypedDict):
    messages: Annotated[Messages, add_messages]
    guard_verdict: NotRequired[GuardVerdict]
    review_verdict: NotRequired[ReviewVerdict]


class PlannerResponse(TypedDict):
    messages: Messages


class GuardResponse(TypedDict):
    guard_verdict: GuardVerdict


class ExecutorResponse(TypedDict):
    messages: list[ToolMessage]


class VerifierResponse(TypedDict):
    review_verdict: ReviewVerdict
