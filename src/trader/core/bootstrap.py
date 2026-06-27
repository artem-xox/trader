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
from trader.core.clients import ClobClient, PolymarketClient, TavilyClient
from trader.core.components.executor import Executor
from trader.core.components.guard import Guard
from trader.core.components.planner import Planner
from trader.core.components.responder import Responder
from trader.core.components.selector import Selector
from trader.core.components.verifier import Verifier
from trader.core.models.protocols import Agent
from trader.core.skills import build_registry
from trader.core.tools import build_tools


def get_model(model: str, settings: Settings, *, temperature: float = 0.4) -> BaseChatModel:
    return ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=temperature)


def build_agent(
    settings: Settings | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Agent:
    settings = settings or get_settings()
    
    strong = get_model(settings.openai_model_strong, settings)  # planner
    weak = get_model(settings.openai_model_weak, settings)  # everything else

    polymarket_search, polymarket_market, polymarket_orderbook, web_search, *general = build_tools(
        PolymarketClient(),
        TavilyClient(api_key=settings.tavily_api_key),
        ClobClient(),
    )
    # general = [current_datetime, calculator, web_fetch, think] — read-only helpers
    # available everywhere (every skill and normal mode).
    registry = build_registry(
        polymarket_search, polymarket_market, polymarket_orderbook, web_search, general
    )
    all_tools = [polymarket_search, polymarket_market, polymarket_orderbook, web_search, *general]
    base_tools = [web_search, *general]  # normal mode: web research + general helpers

    # In-memory for now; swap for langgraph-checkpoint-postgres' PostgresSaver in prod.
    checkpointer = checkpointer or InMemorySaver()
    
    return ReActAgent(
        selector=Selector(weak, registry),
        planner=Planner(strong, registry, base_tools),
        guard=Guard(),
        executor=Executor(all_tools),
        responder=Responder(strong, registry),
        verifier=Verifier(),
        checkpointer=checkpointer,
        settings=settings,
    )


@lru_cache
def get_agent() -> Agent:
    return build_agent()
