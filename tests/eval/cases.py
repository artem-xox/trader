"""Eval cases — the YAML-backed source of truth.

An evaluation is *one skill plus its cases*. Cases live in `datasets/<skill>/cases.yaml`
(versioned in git, reviewable in PRs); a backend (LangSmith today) syncs them into a
vendor dataset for a run. A `Case` is deliberately vendor-neutral so the same case drives
any backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_DATASETS = Path(__file__).parent / "datasets"


@dataclass(frozen=True)
class Case:
    id: str
    """Stable slug; also the LangSmith example key."""
    skill: str
    """Which dataset this case belongs to (find / analyze / normal)."""
    input: str
    """The user message to run the agent on (slash command included)."""
    rubric: str
    """Quality-judge criteria. Falls back to the skill's rubric.md when unset."""
    expected_skill: str
    """Skill the selector should pick. Defaults to `skill`; "" skips the routing check."""
    source: str = "handcrafted"
    """How the case was authored: handcrafted | from-trace."""
    trace_id: str | None = None
    """Originating LangSmith trace, when the case was distilled from real traffic."""


def _skill_dir(skill: str) -> Path:
    return _DATASETS / skill


def _default_rubric(skill: str) -> str:
    path = _skill_dir(skill) / "rubric.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def load_cases(skill: str) -> list[Case]:
    """Load every case for a skill, applying the skill defaults."""
    path = _skill_dir(skill) / "cases.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    default_rubric = _default_rubric(skill)
    return [
        Case(
            id=item["id"],
            skill=skill,
            input=item["input"],
            rubric=item.get("rubric") or default_rubric,
            expected_skill=item.get("expected_skill", skill),
            source=item.get("source", "handcrafted"),
            trace_id=item.get("trace_id"),
        )
        for item in raw
    ]


def add_case(case: Case) -> Path:
    """Append a case to its skill's YAML, keeping only fields that differ from defaults."""
    path = _skill_dir(case.skill) / "cases.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []) or []

    entry: dict[str, object] = {"id": case.id, "input": case.input}
    if case.expected_skill != case.skill:
        entry["expected_skill"] = case.expected_skill
    if case.rubric and case.rubric != _default_rubric(case.skill):
        entry["rubric"] = case.rubric
    entry["source"] = case.source
    if case.trace_id:
        entry["trace_id"] = case.trace_id

    raw.append(entry)
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def skills() -> list[str]:
    """Every skill that has a cases.yaml."""
    return sorted(p.name for p in _DATASETS.iterdir() if (p / "cases.yaml").exists())
