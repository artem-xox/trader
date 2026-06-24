"""Evaluators: deterministic checks + LLM-as-judge scores.

Deterministic (stable, CI-gateable):
- `grounding`: every referenced market id came from a tool result — the agent's core trust
  invariant (mirrors the runtime verifier); should stay at 1.0.
- `routing`: the selector picked the expected skill.
- `tool_calls`: how many tool calls the turn made (a metric, not pass/fail).

LLM-as-judge (anchored rubrics, run at temperature 0 — still expect some run-to-run
variance, so treat as signals, not gates):
- `quality`: how well the answer satisfies the case rubric, grounded in the evidence gathered.
- `depth`: analytical rigor / expertise of the answer.
- `tool_use`: how well tools were chosen, timed, and parameterized.

The judge model is configurable (`OPENAI_MODEL_EVAL`, falls back to the strong tier) and
must be at least as capable as the agent it grades.

Each takes a vendor-neutral `EvalSample` and returns a `Score`, or `None` when the check
doesn't apply to that sample.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from tests.eval.cases import Case


@dataclass(frozen=True)
class Score:
    key: str
    value: float
    comment: str | None = None


@dataclass(frozen=True)
class EvalSample:
    """A finished agent turn, projected to exactly what the evaluators need.

    Vendor-neutral and JSON-serializable so a backend can stash it as run output and
    rebuild it when scoring.
    """

    case: Case
    skill: str
    summary: str
    result: dict
    referenced_market_ids: list[str]
    tool_market_ids: list[str]
    num_tool_calls: int
    # Ordered tool calls of the run: each {name, args, result-snippet}. Powers tool-use eval.
    tool_calls: list[dict] = field(default_factory=list)


class Evaluator(Protocol):
    key: str

    async def evaluate(self, sample: EvalSample) -> Score | None: ...


class Grounding:
    """Anti-hallucination: every referenced market id appears in some tool output."""

    key = "grounding"

    async def evaluate(self, sample: EvalSample) -> Score | None:
        referenced = [mid for mid in sample.referenced_market_ids if mid]
        if not referenced:
            return None  # nothing to ground (normal mode, or an honest "no market")
        seen = set(sample.tool_market_ids)
        invented = [mid for mid in referenced if mid not in seen]
        return Score(
            self.key,
            0.0 if invented else 1.0,
            f"invented ids not from any tool: {invented}" if invented else "all ids grounded",
        )


class Routing:
    """The selector chose the expected skill."""

    key = "routing"

    async def evaluate(self, sample: EvalSample) -> Score | None:
        expected = sample.case.expected_skill
        if not expected:
            return None
        actual = sample.skill or "normal"  # empty skill == normal mode
        ok = actual == expected
        return Score(self.key, 1.0 if ok else 0.0, f"expected {expected!r}, got {actual!r}")


class ToolCalls:
    """How many tool calls the turn made. A metric, not pass/fail — surfaces under-research
    (0–1 calls on a question that needs evidence) or runaway loops (many calls)."""

    key = "tool_calls"

    async def evaluate(self, sample: EvalSample) -> Score | None:
        return Score(self.key, float(sample.num_tool_calls), f"{sample.num_tool_calls} tool call(s)")


class _Judgement(BaseModel):
    # Reasoning first, score second: deciding the number AFTER articulating the rationale
    # (chain-of-thought) yields better-calibrated, more reproducible scores.
    reasoning: str = Field(
        description="Concise step-by-step justification (1-4 sentences), written BEFORE "
        "choosing the score. Reference specifics from the answer and evidence."
    )
    score: float = Field(
        description="Final score in [0.0, 1.0], consistent with the reasoning and the "
        "anchored scale in the instructions."
    )


_QUALITY_PROMPT = """You are a strict, calibrated evaluator of a prediction-market research
assistant. Judge ONLY how well the answer satisfies the task and rubric. Ignore writing
style, length, and confident tone — grade substance, not polish.

The user asked:
{input}

The assistant's structured answer (JSON):
{answer}

Evidence the assistant's tools actually returned (what it had to work with):
{evidence}

Grade against these criteria:
{rubric}

Method:
1. Check the answer against each rubric criterion.
2. Check every factual claim against the evidence above — claims must be supported by it,
   not invented or contradicted. Treat an unsupported number or market as a serious fault.
3. Then assign a score on this anchored scale:
- 1.0 — fully meets the rubric; every claim grounded in the evidence; nothing material missing.
- 0.75 — solid; minor gaps or one weakly-supported claim.
- 0.5 — partially useful; notable gaps, generic reasoning, or a claim not backed by evidence.
- 0.25 — mostly inadequate; largely ungrounded or off-target.
- 0.0 — useless, wrong, or fabricated.

An honest "no suitable market found" that is consistent with the evidence is correct, not a
failure. Reserve scores above 0.8 for answers that genuinely clear the bar."""


class Quality:
    """LLM-as-judge against the case's rubric. One judge for every skill."""

    key = "quality"

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model.with_structured_output(_Judgement)

    async def evaluate(self, sample: EvalSample) -> Score | None:
        prompt = _QUALITY_PROMPT.format(
            input=sample.case.input,
            answer=json.dumps(sample.result, ensure_ascii=False, indent=2),
            evidence=_format_trajectory(sample.tool_calls),
            rubric=sample.case.rubric or "General helpfulness, correctness, and clarity.",
        )
        judgement: _Judgement = await self._model.ainvoke(prompt)
        value = max(0.0, min(1.0, judgement.score))
        return Score(self.key, value, judgement.reasoning)


_DEPTH_PROMPT = """You judge the ANALYTICAL DEPTH and EXPERTISE of a prediction-market
assistant's answer — not whether it is correct, but how rigorous and expert it is. Judge
substance, not length or confident tone: a long, fluent answer with no real analysis is shallow.

The user asked:
{input}

The assistant's structured answer (JSON):
{answer}

Evidence its tools actually returned (depth is only credible if it engages with this):
{evidence}

Score on the bar of a top quant analyst who is also a sharp probabilist, using this anchored scale:
- 1.0 — specific, quantitative reasoning; engages the concrete evidence and base rates;
  explicit probabilities with justification; surfaces non-obvious factors and second-order effects.
- 0.75 — mostly rigorous; some quantification and evidence, a few thin spots.
- 0.5 — plausible but partly generic; some numbers, shallow justification.
- 0.25 — mostly hand-wavy; little real engagement with the evidence.
- 0.0 — vague; no real numbers or evidence; could have been written without looking at the market.

Reward genuine depth, penalize fluff and unsupported confidence."""


class Depth:
    """LLM-as-judge focused only on analytical depth / expertise, independent of `quality`."""

    key = "depth"

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model.with_structured_output(_Judgement)

    async def evaluate(self, sample: EvalSample) -> Score | None:
        if not sample.skill:
            return None  # depth/expertise is a domain-analysis metric; skip normal-mode tasks
        prompt = _DEPTH_PROMPT.format(
            input=sample.case.input,
            answer=json.dumps(sample.result, ensure_ascii=False, indent=2),
            evidence=_format_trajectory(sample.tool_calls),
        )
        judgement: _Judgement = await self._model.ainvoke(prompt)
        value = max(0.0, min(1.0, judgement.score))
        return Score(self.key, value, judgement.reasoning)


def _format_trajectory(tool_calls: list[dict]) -> str:
    if not tool_calls:
        return "(no tools were called)"
    lines = []
    for i, call in enumerate(tool_calls, 1):
        args = json.dumps(call.get("args", {}), ensure_ascii=False)
        result = (call.get("result") or "").replace("\n", " ").strip()
        lines.append(f"{i}. {call['name']}({args})\n   → returned: {result or '(empty)'}")
    return "\n".join(lines)


_TOOL_USE_PROMPT = """You evaluate HOW WELL an assistant used its tools on a single turn —
the trajectory, NOT the final answer's quality.

The user asked:
{input}

The tools it called, in order — name, arguments, and a snippet of what each returned:
{trajectory}

Score 0.0-1.0 on tool-use skill:
- Right tool for the need, called at the right time (gather evidence BEFORE answering)?
- Well-formed, well-targeted arguments — specific and correctly-shaped queries/slugs, not
  vague, malformed, or non-distinctive (e.g. a market search should use a short distinctive
  keyword, not a long literal phrase)?
- No waste — no redundant repeats of the same call, no obviously useless calls, and it did
  not give up after one empty result when a reformulation was warranted?

Anchored scale:
- 1.0 — decisive, well-parameterized, no waste; each call clearly advanced the task.
- 0.75 — effective overall, with one weak param choice or a minor detour.
- 0.5 — got there but with vague params, a redundant call, or a needless detour.
- 0.25 — mostly mis-targeted or wasteful; tools barely helped.
- 0.0 — flailing, mis-targeted, or skipped tools the task clearly needed.
If no tools were called, score on whether the task plausibly needed them (1.0 if it
genuinely did not, low if it did). Judge the trajectory, not the final answer's quality."""


class ToolUse:
    """LLM-as-judge on tool-use quality: did it pick the right tools, at the right time,
    with good parameters, and without waste? Independent of the answer's quality."""

    key = "tool_use"

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model.with_structured_output(_Judgement)

    async def evaluate(self, sample: EvalSample) -> Score | None:
        prompt = _TOOL_USE_PROMPT.format(
            input=sample.case.input,
            trajectory=_format_trajectory(sample.tool_calls),
        )
        judgement: _Judgement = await self._model.ainvoke(prompt)
        value = max(0.0, min(1.0, judgement.score))
        return Score(self.key, value, judgement.reasoning)
