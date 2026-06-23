"""Data schemas shared across the agent core: graph state and verdict types."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph.message import add_messages

from trader.core.models.domain import SkillResult

# The conversation passed in/out of the agent. New messages are appended to the
# per-thread state owned by the graph checkpointer (keyed by thread_id).
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
    # Active skill *name* for this turn; "" (or absent) means normal mode. We store the
    # name (not the Skill object) because the checkpointer serializes the state, and a
    # Skill carries non-serializable tools/schema; the nodes resolve it via the registry.
    skill: NotRequired[str]
    # Number of planner (reasoning) steps taken so far — the real loop budget.
    iteration: NotRequired[int]
    guard_verdict: NotRequired[GuardVerdict]
    review_verdict: NotRequired[ReviewVerdict]
    # The structured final answer, produced by the responder before the loop ends.
    result: NotRequired[SkillResult]


class SelectorResponse(TypedDict):
    skill: str


class PlannerResponse(TypedDict):
    messages: Messages
    iteration: int


class GuardResponse(TypedDict):
    guard_verdict: GuardVerdict
    # Feedback appended to the conversation when a plan is blocked, so the planner can revise.
    messages: NotRequired[Messages]


class ExecutorResponse(TypedDict):
    messages: list[ToolMessage]


class ResponderResponse(TypedDict):
    result: SkillResult
    messages: Messages


class VerifierResponse(TypedDict):
    review_verdict: ReviewVerdict
    # Feedback appended to the conversation when the answer is rejected, so the planner can revise.
    messages: NotRequired[Messages]
