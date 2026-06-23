"""LLM smoke tests for the skill router (the `skills` node)."""

from __future__ import annotations

import json

import pytest

from trader.core.models.domain import GeneralAnswer, MarketAnalysis, ResearchResult


async def test_find_via_explicit_command(run_state):
    """A "/find ..." message deterministically activates the find skill."""
    state = await run_state("/find bitcoin price in 2026")
    assert state["skill"] == "find"
    assert isinstance(state["result"], ResearchResult)


async def test_find_via_intent(run_with_tools):
    """No slash command, but the request clearly matches the find skill."""
    result, tools = await run_with_tools(
        "Find me some interesting Polymarket bets about the 2026 World Cup."
    )
    assert isinstance(result, ResearchResult)
    assert "polymarket_search" in tools


async def test_analyze_via_command(run_state):
    """A "/analyze <url>" message activates the analyze skill and returns a risk model.

    Uses a live market URL so the test never depends on a perishable hard-coded slug.
    """
    from trader.core.clients import PolymarketClient

    raw = await PolymarketClient().search("trump", limit=1)
    try:
        markets = json.loads(raw)
    except json.JSONDecodeError:
        pytest.skip(f"no live Polymarket market available to analyze: {raw}")
    url = markets[0]["url"]

    state = await run_state(f"/analyze {url}")
    assert state["skill"] == "analyze"
    result = state["result"]
    assert isinstance(result, MarketAnalysis)
    # market_id is verifier-enforced: it must come from the polymarket tool output.
    assert result.market_id


async def test_normal_mode_off_domain(run_state):
    """An off-domain question routes to normal mode, not a skill."""
    state = await run_state("What is the capital of France? Answer in one word.")
    assert state["skill"] == ""
    assert isinstance(state["result"], GeneralAnswer)
    assert "paris" in state["result"].summary.lower()
