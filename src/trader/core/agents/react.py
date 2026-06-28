"""Custom ReAct agent.

This module owns only the loop topology — the transitions between components and how
they compile into a graph. The behaviour lives in `trader.core.components`; the model
and checkpointer are injected (see `trader.core.bootstrap`).

    START → skills → planner ──tool_calls?──→ guard ──allow?──→ executor ──budget?──→ planner
                             │                     └──block───→ planner   │  (else)    └─→ responder
                             └──final answer──────────────────────────────→ responder → verifier ──ok?──→ END
                                                                                                  └──revise──→ planner

The `skills` node picks at most one skill for the turn (or normal mode); the planner,
guard and responder adapt to it. The loop budget is the `iteration` counter (planner
steps), not `recursion_limit`: once it is exhausted the executor routes straight to the
responder (so the requested tools still run and the history stays valid) and the verifier
stops revising.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from trader.common.config import Settings
from trader.core.agents.base import BaseAgent, silent_router
from trader.core.models.domain import SkillResult
from trader.core.models.protocols import Executor, Guard, Planner, Responder, Selector, Verifier
from trader.core.models.schemas import AgentState, GuardVerdict, Messages, PlannerAction, ReviewVerdict
from trader.core.models.streaming import ProgressEvent

# Tool-call args worth surfacing as a status hint, in priority order. Ids/tokens are left
# out on purpose — they are noise, not signal, for a human watching progress.
_HINT_KEYS = ("query", "slug", "url", "expression", "thought")


def _arg_hint(args: dict) -> str | None:
    for key in _HINT_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return None


def _status_for(node: str, update: dict) -> ProgressEvent | None:
    """Map a node's state update to a progress event, or None for silent nodes."""
    if node == "skills":
        skill = update.get("skill")
        return ProgressEvent(label=f"skill:{skill}") if skill else None
    if node == "planner":
        calls = getattr(update["messages"][-1], "tool_calls", None)
        if not calls:
            return None  # drafted an answer → the responder announces "synthesize" next
        first, extra = calls[0], len(calls) - 1
        hint = _arg_hint(first.get("args", {}))
        detail = f"{hint} (+{extra})" if hint and extra else hint or (f"+{extra}" if extra else None)
        return ProgressEvent(label=f"tool:{first['name']}", detail=detail)
    if node == "responder":
        return ProgressEvent(label="synthesize")
    if node == "verifier" and update.get("review_verdict") == ReviewVerdict.REVISE:
        return ProgressEvent(label="revise")
    return None  # guard, executor, accepted verifier: nothing worth showing


class ReActAgent(BaseAgent):

    AGENT_NAME = "react"

    def __init__(
        self,
        *,
        selector: Selector,
        planner: Planner,
        guard: Guard,
        executor: Executor,
        responder: Responder,
        verifier: Verifier,
        checkpointer: BaseCheckpointSaver,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(settings)
        self._selector = selector
        self._planner = planner
        self._guard = guard
        self._executor = executor
        self._responder = responder
        self._verifier = verifier
        self._checkpointer = checkpointer
        self._graph = self._build_graph()

    def _route_after_planner(self, state: AgentState) -> PlannerAction:
        """Tool calls → gate them; otherwise the planner drafted an answer → synthesize."""
        last = state["messages"][-1]
        return PlannerAction.ACT if getattr(last, "tool_calls", None) else PlannerAction.ANSWER

    def _route_after_guard(self, state: AgentState) -> GuardVerdict:
        """Allowed tool calls → execute; blocked → back to the planner to revise."""
        return state.get("guard_verdict", GuardVerdict.ALLOW)

    def _route_after_executor(self, state: AgentState) -> str:
        """Budget left → keep reasoning; exhausted → synthesize with what we have."""
        if state.get("iteration", 0) >= self._settings.agent_max_iterations:
            return "responder"
        return "planner"

    def _route_after_verifier(self, state: AgentState) -> ReviewVerdict:
        """Accepted answer → finish; reject → revise, unless the budget is exhausted."""
        verdict = state.get("review_verdict", ReviewVerdict.OK)
        if verdict == ReviewVerdict.REVISE and state.get("iteration", 0) >= self._settings.agent_max_iterations:
            return ReviewVerdict.OK
        return verdict

    def _build_graph(self):
        """Build the ReAct graph."""

        builder = StateGraph(AgentState)

        # Retry the nodes that hit the LLM/network on transient failures (connection
        # errors, 5xx, rate limits). The default policy skips deterministic errors like
        # ValueError/ValidationError, so a bad parse fails fast instead of looping.
        retry = RetryPolicy()

        builder.add_node("skills", self._selector, retry_policy=retry)
        builder.add_node("planner", self._planner, retry_policy=retry)
        builder.add_node("guard", self._guard)
        builder.add_node("executor", self._executor)
        builder.add_node("responder", self._responder, retry_policy=retry)
        builder.add_node("verifier", self._verifier)

        builder.add_edge(START, "skills")
        builder.add_edge("skills", "planner")
        builder.add_conditional_edges(
            "planner",
            silent_router(self._route_after_planner),
            {PlannerAction.ACT: "guard", PlannerAction.ANSWER: "responder"},
        )
        builder.add_conditional_edges(
            "guard",
            silent_router(self._route_after_guard),
            {GuardVerdict.ALLOW: "executor", GuardVerdict.BLOCK: "planner"},
        )
        builder.add_conditional_edges(
            "executor",
            silent_router(self._route_after_executor),
            {"planner": "planner", "responder": "responder"},
        )
        builder.add_edge("responder", "verifier")
        builder.add_conditional_edges(
            "verifier",
            silent_router(self._route_after_verifier),
            {ReviewVerdict.OK: END, ReviewVerdict.REVISE: "planner"},
        )

        return builder.compile(name=self.AGENT_NAME, checkpointer=self._checkpointer)

    def _config(self, thread_id: str | None) -> dict:
        return {
            "recursion_limit": self._settings.agent_max_iterations * 6 + 10,
            "configurable": {"thread_id": thread_id or "default"},
        }

    async def invoke(self, messages: Messages, *, thread_id: str | None = None) -> SkillResult:
        result = await self._graph.ainvoke({"messages": messages}, config=self._config(thread_id))
        return result["result"]

    async def astream(
        self, messages: Messages, *, thread_id: str | None = None
    ) -> AsyncIterator[ProgressEvent]:
        """Stream per-node progress, then a terminal `final` event carrying the result.

        Uses LangGraph's "updates" mode: each node's state delta becomes at most one status
        event. The responder's delta holds the result; we keep the latest (the verifier may
        send the loop back to revise) and emit it once the graph run completes.
        """
        result: SkillResult | None = None
        async for chunk in self._graph.astream(
            {"messages": messages}, config=self._config(thread_id), stream_mode="updates"
        ):
            for node, update in chunk.items():
                if update and "result" in update:
                    result = update["result"]
                event = _status_for(node, update)
                if event is not None:
                    yield event
        if result is not None:
            yield ProgressEvent(kind="final", result=result)
