"""Skill registry assembly."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from langchain_core.tools import BaseTool

from trader.core.skills.analyze import analyze_skill
from trader.core.skills.base import Skill, SkillRegistry
from trader.core.skills.find import find_skill
from trader.core.tools import PolymarketTools

__all__ = ["Skill", "SkillRegistry", "build_registry"]


def build_registry(
    polymarket: PolymarketTools,
    general: Sequence[BaseTool] = (),
) -> SkillRegistry:
    skills = [
        find_skill(polymarket.search, polymarket.tradability),
        analyze_skill(polymarket.market, polymarket.search, polymarket.orderbook),
    ]
    # General read-only helpers (web search/fetch, calculator, current time, think) are
    # available to every skill, in addition to its own tools.
    skills = [replace(skill, tools=skill.tools + tuple(general)) for skill in skills]
    return SkillRegistry(skills)
