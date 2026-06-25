"""Skill registry assembly."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from langchain_core.tools import BaseTool

from trader.core.skills.analyze import analyze_skill
from trader.core.skills.base import Skill, SkillRegistry
from trader.core.skills.find import find_skill

__all__ = ["Skill", "SkillRegistry", "build_registry"]


def build_registry(
    polymarket_search: BaseTool,
    polymarket_market: BaseTool,
    polymarket_orderbook: BaseTool,
    web_search: BaseTool,
    general: Sequence[BaseTool] = (),
) -> SkillRegistry:
    skills = [
        find_skill(polymarket_search, web_search),
        analyze_skill(polymarket_market, polymarket_search, polymarket_orderbook, web_search),
    ]
    # General read-only helpers (calculator, current time, web fetch) are available to
    # every skill, in addition to its own tools.
    skills = [replace(skill, tools=skill.tools + tuple(general)) for skill in skills]
    return SkillRegistry(skills)
