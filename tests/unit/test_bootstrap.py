"""Wiring tests for the composition root (no network / LLM calls)."""

from __future__ import annotations

from trader.common.config import Settings
from trader.core.bootstrap import build_agent


def test_planner_uses_strong_model_others_weak():
    settings = Settings(
        openai_model_strong="strong-x",
        openai_model_weak="weak-y",
        openai_api_key="dummy",
        tavily_api_key="dummy",
    )
    agent = build_agent(settings)

    assert agent._planner._model.model_name == "strong-x"
    assert agent._responder._model.model_name == "weak-y"
