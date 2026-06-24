"""Run the agent for a case and project the result to an `EvalSample`.

This is the vendor-neutral seam: `run_agent` knows how to drive *this* agent and extract
what the evaluators need; the `EvalBackend` protocol knows how to host a run (sync the
dataset, link traces, push scores) for a given vendor. The CLI wires the two together.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from langchain_core.messages import HumanMessage

from tests.eval.cases import Case
from tests.eval.evaluators import EvalSample, Evaluator
from trader.core.components.verifier import _market_ids_seen
from trader.core.models.protocols import Agent


async def run_agent(agent: Agent, case: Case) -> EvalSample:
    """Run one case on a fresh thread and project the final graph state to an EvalSample.

    Reaches into the compiled graph (like the LLM-test fixtures) because evaluators need
    the chosen skill and the tool outputs, not just the public `SkillResult`.
    """
    state = await agent._graph.ainvoke(  # type: ignore[attr-defined]
        {"messages": [HumanMessage(case.input)]},
        config={
            "recursion_limit": agent._settings.agent_max_iterations * 6 + 10,  # type: ignore[attr-defined]
            "configurable": {"thread_id": uuid.uuid4().hex},
        },
    )
    result = state["result"]
    num_tool_calls = sum(1 for m in state["messages"] if getattr(m, "type", None) == "tool")
    return EvalSample(
        case=case,
        skill=state.get("skill", ""),
        summary=result.summary,
        result=result.model_dump(),
        referenced_market_ids=result.referenced_market_ids(),
        tool_market_ids=sorted(_market_ids_seen(state)),
        num_tool_calls=num_tool_calls,
    )


class EvalBackend(Protocol):
    """Hosts an evaluation run for a vendor (datasets, trace linkage, scores)."""

    async def run(self, skill: str, cases: list[Case], evaluators: list[Evaluator]) -> str:
        """Run every case, score it, and return a human-pointer to the results (e.g. URL)."""
        ...
