"""Run the agent for a case and project the result to an `EvalSample`.

This is the vendor-neutral seam: `run_agent` knows how to drive *this* agent and extract
what the evaluators need; the `EvalBackend` protocol knows how to host a run (sync the
dataset, link traces, push scores) for a given vendor. The CLI wires the two together.
"""

from __future__ import annotations

import os
import uuid
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from langchain_core.messages import HumanMessage
from langsmith import tracing_context

from tests.eval.cases import Case
from tests.eval.evaluators import EvalSample, Evaluator
from trader.core.components.verifier import _market_ids_seen
from trader.core.models.protocols import Agent


# Tool results shown to the LLM judges (quality/depth/tool_use). A polymarket_search
# returns ~4 KB for 8 markets, so a tight cap starved the judge of evidence and made it
# flag genuinely-grounded suggestions (ids confirmed by the deterministic `grounding`=1.0)
# as "invented". Keep enough that the judge sees what the agent actually saw.
_RESULT_SNIPPET_CHARS = 6000


def eval_tracing() -> AbstractContextManager:
    """Suppress nested LangSmith runs during eval unless EVAL_TRACE is set.

    `aevaluate` always records each example's root run and its scores; what burns quota is
    the *nested* agent/judge LLM and tool runs hung under those roots. Wrapping the agent
    and judge calls in `tracing_context(enabled=False)` drops those children while keeping
    the roots and feedback (so summarize() still works, minus native cost/token totals).
    Set EVAL_TRACE=true (e.g. `make eval TRACE=true`) to keep full traces for debugging.
    """
    if os.getenv("EVAL_TRACE", "").lower() in ("1", "true", "yes"):
        return nullcontext()
    return tracing_context(enabled=False)


def _tool_trajectory(messages: list) -> list[dict]:
    """Reconstruct the ordered tool calls of a run: each call's name, args, and a snippet
    of what it returned. This is what tool-use evaluators reason over."""
    results_by_id: dict[str, str] = {}
    for message in messages:
        if getattr(message, "type", None) == "tool":
            results_by_id[message.tool_call_id] = str(message.content)

    trajectory: list[dict] = []
    for message in messages:
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            trajectory.append(
                {
                    "name": call["name"],
                    "args": call.get("args", {}),
                    "result": results_by_id.get(call["id"], "")[:_RESULT_SNIPPET_CHARS],
                }
            )
    return trajectory


async def run_agent(agent: Agent, case: Case) -> EvalSample:
    """Run one case on a fresh thread and project the final graph state to an EvalSample.

    Reaches into the compiled graph (like the LLM-test fixtures) because evaluators need
    the chosen skill and the tool outputs, not just the public `SkillResult`.
    """
    with eval_tracing():
        state = await agent._graph.ainvoke(  # type: ignore[attr-defined]
            {"messages": [HumanMessage(case.input)]},
            config={
                "recursion_limit": agent._settings.agent_max_iterations * 6 + 10,  # type: ignore[attr-defined]
                "configurable": {"thread_id": uuid.uuid4().hex},
            },
        )
    result = state["result"]
    tool_calls = _tool_trajectory(state["messages"])
    return EvalSample(
        case=case,
        skill=state.get("skill", ""),
        summary=result.summary,
        result=result.model_dump(),
        referenced_market_ids=result.referenced_market_ids(),
        tool_market_ids=sorted(_market_ids_seen(state)),
        num_tool_calls=len(tool_calls),
        tool_calls=tool_calls,
    )


class EvalBackend(Protocol):
    """Hosts an evaluation run for a vendor (datasets, trace linkage, scores)."""

    async def run(
        self,
        skill: str,
        cases: list[Case],
        evaluators: list[Evaluator],
        *,
        experiment_name: str | None = None,
    ) -> str:
        """Run every case, score it, and return a human-pointer to the results (e.g. URL)."""
        ...
