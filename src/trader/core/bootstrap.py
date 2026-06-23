"""Composition root: build a fully-assembled agent from settings.

This is the single place that picks the concrete LLM and wires it into the agent, so the
rest of the app depends only on the assembled agent (and the `Agent` protocol).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from trader.common.config import Settings, get_settings
from trader.core.agents.react import ReActAgent
from trader.core.components.executor import Executor
from trader.core.components.guard import Guard
from trader.core.components.planner import Planner
from trader.core.components.verifier import Verifier
from trader.core.models.protocols import Agent
from trader.core.prompts import SYSTEM_PROMPT
from trader.core.tools import ALL_TOOLS


def get_model(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.4,
    )


def build_agent(settings: Settings | None = None) -> Agent:
    settings = settings or get_settings()
    model = get_model(settings)
    return ReActAgent(
        planner=Planner(model, ALL_TOOLS, SYSTEM_PROMPT),
        executor=Executor(ALL_TOOLS),
        verifier=Verifier(),
        guard=Guard(model),
        settings=settings,
    )


@lru_cache
def get_agent() -> Agent:
    return build_agent()
