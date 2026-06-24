"""Evaluators — deliberately few.

Three, by design:
- `grounding` (deterministic): every market id the answer references must come from a tool
  result. This is the agent's core trust invariant (mirrors the runtime verifier) and the
  one score that should stay at 1.0.
- `routing` (deterministic): the selector picked the skill the case expects.
- `quality` (LLM judge): how well the structured answer satisfies the case's rubric.

Each takes a vendor-neutral `EvalSample` and returns a `Score`, or `None` when the check
doesn't apply to that sample.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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
        ok = sample.skill == expected
        return Score(self.key, 1.0 if ok else 0.0, f"expected {expected!r}, got {sample.skill!r}")


_QUALITY_PROMPT = """You are a strict evaluator of a prediction-market research assistant.

The user asked:
{input}

The assistant produced this structured answer (JSON):
{answer}

Grade it against these criteria:
{rubric}

Return a score from 0.0 (useless / wrong) to 1.0 (excellent), and a one or two sentence
justification. Be exacting: reserve scores above 0.8 for answers that genuinely meet the bar."""


class _Judgement(BaseModel):
    score: float = Field(description="Quality from 0.0 (useless) to 1.0 (excellent).")
    comment: str = Field(description="One or two sentences justifying the score.")


class Quality:
    """LLM-as-judge against the case's rubric. One judge for every skill."""

    key = "quality"

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model.with_structured_output(_Judgement)

    async def evaluate(self, sample: EvalSample) -> Score | None:
        prompt = _QUALITY_PROMPT.format(
            input=sample.case.input,
            answer=json.dumps(sample.result, ensure_ascii=False, indent=2),
            rubric=sample.case.rubric or "General helpfulness, correctness, and clarity.",
        )
        judgement: _Judgement = await self._model.ainvoke(prompt)
        value = max(0.0, min(1.0, judgement.score))
        return Score(self.key, value, judgement.comment)
