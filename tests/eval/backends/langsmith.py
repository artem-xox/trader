"""LangSmith backend — the only module that imports the vendor SDK.

It maps our vendor-neutral primitives onto LangSmith's native machinery: cases become
dataset examples, a run becomes an `aevaluate` experiment (so every turn is a linked
trace), and our `Score`s become feedback. Swapping in Langfuse later means another module
implementing the same `EvalBackend` protocol — nothing else changes.
"""

from __future__ import annotations

from langsmith import Client, aevaluate

from tests.eval.cases import Case
from tests.eval.evaluators import EvalSample, Evaluator
from tests.eval.runner import run_agent
from trader.core.models.protocols import Agent


def _dataset_name(skill: str) -> str:
    return f"trader-eval-{skill}"


def _sample_payload(sample: EvalSample) -> dict:
    """The serializable slice of an EvalSample stored as the run's output."""
    return {
        "skill": sample.skill,
        "summary": sample.summary,
        "result": sample.result,
        "referenced_market_ids": sample.referenced_market_ids,
        "tool_market_ids": sample.tool_market_ids,
        "num_tool_calls": sample.num_tool_calls,
    }


class LangSmithBackend:
    def __init__(self, agent: Agent, client: Client | None = None) -> None:
        self._agent = agent
        self._client = client or Client()

    def _sync(self, skill: str, cases: list[Case]) -> None:
        """Upsert the skill's dataset to exactly the current YAML cases."""
        name = _dataset_name(skill)
        if self._client.has_dataset(dataset_name=name):
            for example in self._client.list_examples(dataset_name=name):
                self._client.delete_example(example.id)
        else:
            self._client.create_dataset(name, description=f"Trader eval cases — {skill} skill")
        self._client.create_examples(
            dataset_name=name,
            examples=[
                {
                    "inputs": {"id": case.id, "input": case.input},
                    "outputs": {"expected_skill": case.expected_skill, "rubric": case.rubric},
                    "metadata": {"skill": case.skill, "source": case.source, "trace_id": case.trace_id},
                }
                for case in cases
            ],
        )

    async def run(self, skill: str, cases: list[Case], evaluators: list[Evaluator]) -> str:
        self._sync(skill, cases)
        by_id = {case.id: case for case in cases}

        async def target(inputs: dict) -> dict:
            return _sample_payload(await run_agent(self._agent, by_id[inputs["id"]]))

        results = await aevaluate(
            target,
            data=_dataset_name(skill),
            evaluators=[_adapt(ev, by_id) for ev in evaluators],
            experiment_prefix=f"trader-{skill}",
            client=self._client,
            max_concurrency=2,
        )
        return results.experiment_name

    def summarize(self, experiment_name: str) -> dict:
        """Aggregate an experiment: mean of each score + native cost/token totals.

        Cost and tokens are computed by LangSmith on each root run, so we read them rather
        than recomputing. Cost aggregation can lag a beat after the run; missing values are
        simply skipped.
        """
        runs = list(self._client.list_runs(project_name=experiment_name, is_root=True))
        scores: dict[str, list[float]] = {}
        costs: list[float] = []
        tokens: list[int] = []
        for run in runs:
            for fb in self._client.list_feedback(run_ids=[run.id]):
                if fb.score is not None:
                    scores.setdefault(fb.key, []).append(fb.score)
            if run.total_cost is not None:
                costs.append(float(run.total_cost))
            if run.total_tokens is not None:
                tokens.append(int(run.total_tokens))
        means = {key: sum(vals) / len(vals) for key, vals in scores.items()}
        return {
            "cases": len(runs),
            "means": means,
            "total_cost": sum(costs) if costs else None,
            "total_tokens": sum(tokens) if tokens else None,
        }

    def read_case_from_trace(
        self, trace_id: str, skill: str, *, case_id: str | None = None, rubric: str | None = None
    ) -> Case:
        """Distill a case from a real trace: pull the user message off the run."""
        run = self._client.read_run(trace_id)
        return Case(
            id=case_id or f"{skill}-{trace_id[:8]}",
            skill=skill,
            input=_extract_input(run.inputs),
            rubric=rubric or "",
            expected_skill=skill,
            source="from-trace",
            trace_id=trace_id,
        )


def _adapt(evaluator: Evaluator, by_id: dict[str, Case]):
    """Wrap our Evaluator into LangSmith's (run, example) feedback function."""

    async def _fn(run, example):
        payload = run.outputs or {}
        sample = EvalSample(
            case=by_id[example.inputs["id"]],
            skill=payload.get("skill", ""),
            summary=payload.get("summary", ""),
            result=payload.get("result", {}),
            referenced_market_ids=payload.get("referenced_market_ids", []),
            tool_market_ids=payload.get("tool_market_ids", []),
            num_tool_calls=payload.get("num_tool_calls", 0),
        )
        score = await evaluator.evaluate(sample)
        if score is None:
            return {"results": []}  # not applicable — emit no feedback (no stray key)
        return {"results": [{"key": score.key, "score": score.value, "comment": score.comment}]}

    _fn.__name__ = evaluator.key
    return _fn


def _extract_input(inputs: dict | None) -> str:
    """Best-effort: find the user message text in a run's inputs."""
    if not inputs:
        return ""
    messages = inputs.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            return str(last.get("content") or last.get("kwargs", {}).get("content", ""))
        return str(last)
    for key in ("message", "input", "text"):
        if key in inputs:
            return str(inputs[key])
    return ""
