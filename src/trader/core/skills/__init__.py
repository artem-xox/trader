"""Skill registry assembly."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from trader.core.skills.analyze import analyze_skill
from trader.core.skills.base import Skill, SkillRegistry
from trader.core.skills.find import find_skill

__all__ = ["Skill", "SkillRegistry", "build_registry"]


def build_registry(
    polymarket_search: BaseTool,
    polymarket_market: BaseTool,
    web_search: BaseTool,
) -> SkillRegistry:
    return SkillRegistry(
        [
            find_skill(polymarket_search, web_search),
            analyze_skill(polymarket_market, polymarket_search, web_search),
        ]
    )
