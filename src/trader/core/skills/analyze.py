"""The `analyze` skill: a deep dive on a single Polymarket market with a risk model.

Given a market URL (or description), it fetches the market's full detail, gathers context,
and produces a `MarketAnalysis` — a directional call with a fair-probability estimate and
an explicit risk assessment.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from trader.core.models.domain import MarketAnalysis
from trader.core.skills.base import Skill

_PLANNER_PROMPT = """You are now acting as a prediction-market analyst doing a deep dive on
ONE Polymarket market.

1. The user gives a market URL (or a description). Extract the slug — the last path segment
   of the URL — and call `polymarket_market` with it to get the market's detail, including
   its resolution criteria and `clob_token_ids`. If you only have a description, find the
   market with `polymarket_search` first: search with short English keywords for the most
   distinctive entity (a name, e.g. "Jesus", "Bitcoin"), not a long literal or non-English
   phrase. If the first query returns nothing relevant, reformulate and try again (a few
   attempts) before concluding no market exists.
2. Once you have the market, call `polymarket_orderbook` with the first element of its
   `clob_token_ids` to get live execution data: spread, depth, and price volatility.
   This tells you whether a theoretical edge survives real trading costs.
3. Use `web_search` to gather the current real-world situation relevant to how the market
   resolves.
4. Form your own estimate of the true probability, compare it to the market's implied
   probability (the edge), and assess the risks (liquidity, time horizon, resolution
   ambiguity, headline/tail risk). Factor in the orderbook data: a wide spread or thin
   depth narrows or kills the edge after costs.

Never invent a market — analyze only a market returned by the tools. If the slug matches an
event with several markets, focus on the single most relevant one.
"""

_GUARD_PROMPT = """The active skill is read-only analysis of one Polymarket market. The
expected tools (market lookup, market search, web search, and general read-only helpers —
a calculator, the current date/time, and fetching a page) are all read-only — allow them
freely. This skill performs no trading or money-moving actions.
"""

_RESPONDER_PROMPT = """You are finalizing a deep dive on a single Polymarket market.

Read the conversation above (the market detail and the research) and produce the analysis:
- `summary`: a short natural-language verdict for the user.
- the structured fields: implied vs. fair probability, the edge, your stance
  (lean_yes / lean_no / pass), confidence, key factors, and a risk assessment.

Hard rules:
- The `market_id`, `url` and `resolution_criteria` must come from the polymarket tool
  results — never invent them.
- Ground the edge and key factors in the evidence gathered, not generic reasoning.
"""


def analyze_skill(
    polymarket_market: BaseTool,
    polymarket_search: BaseTool,
    polymarket_orderbook: BaseTool,
    web_search: BaseTool,
) -> Skill:
    return Skill(
        name="analyze",
        triggers=("analyze",),
        description="Evaluate ONE specific Polymarket bet (by URL or description): fair-value estimate, edge, stance, and risk.",
        planner_prompt=_PLANNER_PROMPT,
        guard_prompt=_GUARD_PROMPT,
        responder_prompt=_RESPONDER_PROMPT,
        output_schema=MarketAnalysis,
        tools=(polymarket_market, polymarket_search, polymarket_orderbook, web_search),
    )
