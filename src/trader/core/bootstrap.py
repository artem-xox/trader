"""Composition root: build a fully-assembled agent from settings.

This is the single place that picks the concrete LLM, instantiates external clients,
tools and skills, and wires them into the agent, so the rest of the app depends only on
the assembled agent (and the `Agent` protocol).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from trader.common.config import Settings, get_settings
from trader.core.agents.react import ReActAgent
from trader.core.clients import PolymarketClient, TavilyClient
from trader.core.components.executor import Executor
from trader.core.components.guard import Guard
from trader.core.components.planner import Planner
from trader.core.components.responder import Responder
from trader.core.components.selector import Selector
from trader.core.components.verifier import Verifier
from trader.core.models.domain import GeneralAnswer
from trader.core.models.protocols import Agent
from trader.core.prompts import BASE_GUARD_PROMPT, BASE_PLANNER_PROMPT, BASE_RESPONDER_PROMPT
from trader.core.skills import build_registry
from trader.core.tools import build_tools


def get_model(model: str, settings: Settings) -> BaseChatModel:
    return ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=0.4)


def build_agent(
    settings: Settings | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Agent:
    settings = settings or get_settings()
    strong = get_model(settings.openai_model_strong, settings)  # planner
    weak = get_model(settings.openai_model_weak, settings)  # everything else

    polymarket_search, polymarket_market, web_search = build_tools(
        PolymarketClient(),
        TavilyClient(api_key=settings.tavily_api_key),
    )
    registry = build_registry(polymarket_search, polymarket_market, web_search)
    all_tools = [polymarket_search, polymarket_market, web_search]
    base_tools = [web_search]  # normal mode: general-purpose research only

    # In-memory for now; swap for langgraph-checkpoint-postgres' PostgresSaver in prod.
    checkpointer = checkpointer or InMemorySaver()
    return ReActAgent(
        selector=Selector(weak, registry),
        planner=Planner(strong, registry, BASE_PLANNER_PROMPT, base_tools),
        guard=Guard(weak, registry, BASE_GUARD_PROMPT),
        executor=Executor(all_tools),
        responder=Responder(weak, registry, BASE_RESPONDER_PROMPT, GeneralAnswer),
        verifier=Verifier(),
        checkpointer=checkpointer,
        settings=settings,
    )


@lru_cache
def get_agent() -> Agent:
    return build_agent()
