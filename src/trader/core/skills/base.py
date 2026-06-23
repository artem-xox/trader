"""Skill abstraction and registry.

A `Skill` is a *specialization* of the base ReAct loop, not a procedure: it bundles the
prompt knowledge, output schema, and tools that turn the generic agent into a focused
one (e.g. the `find` skill turns it into a Polymarket research analyst). The `skills`
node picks at most one skill per turn and records its name in the graph state; each node
then resolves the active skill from the registry and adapts.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from trader.core.models.domain import SkillResult


@dataclass(frozen=True)
class Skill:
    name: str
    """Stable identifier stored in the graph state."""
    triggers: tuple[str, ...]
    """Slash-command names that explicitly invoke this skill, e.g. ("find",)."""
    description: str
    """One line used by the selector for intent matching and by help text."""
    planner_prompt: str
    """Appended to the base planner prompt when this skill is active."""
    guard_prompt: str
    """Appended to the base guard prompt when this skill is active."""
    responder_prompt: str
    """Replaces the base responder prompt; explains the skill's output schema."""
    output_schema: type[SkillResult]
    """Structured shape the responder produces for this skill."""
    tools: tuple[BaseTool, ...]
    """Tools the planner may call while this skill is active."""

    def __post_init__(self) -> None:
        if not issubclass(self.output_schema, BaseModel):
            raise TypeError("output_schema must be a pydantic model")


class SkillRegistry:
    """Holds the available skills and resolves them by name or slash command."""

    def __init__(self, skills: list[Skill]) -> None:
        self._skills = {skill.name: skill for skill in skills}

    def get(self, name: str | None) -> Skill | None:
        """Resolve the active skill, or None for normal mode."""
        return self._skills.get(name) if name else None

    def names(self) -> list[str]:
        return list(self._skills)

    def match_command(self, text: str) -> str | None:
        """Map a leading slash command (e.g. "/find ...") to a skill name, else None."""
        if not text.startswith("/"):
            return None
        command = text[1:].split(maxsplit=1)[0].lower()
        for skill in self._skills.values():
            if command in skill.triggers:
                return skill.name
        return None

    def catalog(self) -> str:
        """Render `name: description` lines for the selector prompt."""
        return "\n".join(f"- {s.name}: {s.description}" for s in self._skills.values())
