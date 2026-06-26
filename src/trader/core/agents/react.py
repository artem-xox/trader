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

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from trader.common.config import Settings
from trader.core.agents.base import BaseAgent
from trader.core.models.domain import SkillResult
from trader.core.models.protocols import Executor, Guard, Planner, Responder, Selector, Verifier
from trader.core.models.schemas import AgentState, GuardVerdict, Messages, PlannerAction, ReviewVerdict


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
            self._route_after_planner,
            {PlannerAction.ACT: "guard", PlannerAction.ANSWER: "responder"},
        )
        builder.add_conditional_edges(
            "guard",
            self._route_after_guard,
            {GuardVerdict.ALLOW: "executor", GuardVerdict.BLOCK: "planner"},
        )
        builder.add_conditional_edges(
            "executor",
            self._route_after_executor,
            {"planner": "planner", "responder": "responder"},
        )
        builder.add_edge("responder", "verifier")
        builder.add_conditional_edges(
            "verifier",
            self._route_after_verifier,
            {ReviewVerdict.OK: END, ReviewVerdict.REVISE: "planner"},
        )

        return builder.compile(name=self.AGENT_NAME, checkpointer=self._checkpointer)

    async def invoke(self, messages: Messages, *, thread_id: str | None = None) -> SkillResult:
        result = await self._graph.ainvoke(
            {"messages": messages},
            config={
                "recursion_limit": self._settings.agent_max_iterations * 6 + 10,
                "configurable": {"thread_id": thread_id or "default"},
            },
        )
        return result["result"]
