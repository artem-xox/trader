"""Custom ReAct agent.

This module owns only the loop topology — the transitions between components and how
they compile into a graph. The behaviour lives in `trader.core.components`; the model is
injected (see `trader.core.bootstrap`).

    START → planner ──tool_calls?──→ guard ──allow?──→ executor → planner
                    │                     └──block───→ planner   (revise plan)
                    └──final answer──→ verifier ──ok?──→ END
                                                └──revise──→ planner
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from trader.common.config import Settings
from trader.core.agents.base import BaseAgent
from trader.core.models.protocols import Executor, Guard, Planner, Verifier
from trader.core.models.schemas import AgentState, GuardVerdict, Messages, PlannerAction, ReviewVerdict


def _route_after_planner(state: AgentState) -> str:
    """Tool calls → gate them; otherwise the planner drafted a final answer → verify."""
    last = state["messages"][-1]
    return "act" if getattr(last, "tool_calls", None) else "answer"


def _route_after_guard(state: AgentState) -> GuardVerdict:
    """Allowed tool calls → execute; blocked → back to the planner to revise."""
    return state.get("guard_verdict", GuardVerdict.ALLOW)


def _route_after_verifier(state: AgentState) -> ReviewVerdict:
    """Accepted answer → finish; otherwise loop back to revise."""
    return state.get("review_verdict", ReviewVerdict.OK)


class ReActAgent(BaseAgent):
    
    AGENT_NAME = "react"
    
    def __init__(
        self,
        *,
        planner: Planner,
        executor: Executor,
        verifier: Verifier,
        guard: Guard,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(settings)
        self._planner = planner
        self._executor = executor
        self._verifier = verifier
        self._guard = guard
        self._graph = self._build_graph()

    def _build_graph(self):
        """Build the ReAct graph."""
        
        builder = StateGraph(AgentState)
        
        builder.add_node("planner", self._planner)
        builder.add_node("guard", self._guard)
        builder.add_node("executor", self._executor)
        builder.add_node("verifier", self._verifier)

        builder.add_edge(START, "planner")
        builder.add_conditional_edges(
            "planner", 
            _route_after_planner, 
            {PlannerAction.ACT: "guard", PlannerAction.ANSWER: "verifier"},
        )
        builder.add_conditional_edges(
            "guard",
            _route_after_guard,
            {GuardVerdict.ALLOW: "executor", GuardVerdict.BLOCK: "planner"},
        )
        builder.add_edge("executor", "planner")
        builder.add_conditional_edges(
            "verifier",
            _route_after_verifier,
            {ReviewVerdict.OK: END, ReviewVerdict.REVISE: "planner"},
        )

        return builder.compile(name=self.AGENT_NAME)

    async def invoke(self, messages: Messages) -> str:
        result = await self._graph.ainvoke(
            {"messages": messages},
            config={"recursion_limit": self._settings.agent_max_iterations * 2},
        )
        final = result["messages"][-1]
        return final.content if isinstance(final.content, str) else str(final.content)
