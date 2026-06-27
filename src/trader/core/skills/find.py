"""The `find` skill: research and rank interesting Polymarket bets on a topic.

This is the behaviour the agent used to have hard-wired. As a skill it owns its own
prompts, its `ResearchResult` output schema, and the polymarket/web search tools.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from trader.core.models.domain import ResearchResult
from trader.core.skills.base import Skill

_PLANNER_PROMPT = """You are now acting as a prediction-market research analyst for Polymarket.

Given the user's topic, find genuinely interesting bets:
1. Use `polymarket_search` to find real, active markets on the topic. One search is rarely
   enough — try a few keyword variations to surface the strongest candidates. For a specific
   Formula 1 race/qualifying or a football match, pass `tag` ('f1' or 'soccer') with the
   event name as the query — plain keyword search misses those per-event sports markets.
2. Use `web_search` to gather current news and facts for the candidates you shortlist, so
   you can judge whether a market's implied probability looks mispriced (the edge). Do not
   rank a market you have gathered no evidence on.
3. Evaluate candidates on: relevance, implied probability vs. your read of reality (edge),
   liquidity/volume, and time horizon.

Never invent markets — only reason about markets returned by the tools, and refer to a
market only by the id and url that appeared verbatim in a tool result.
"""

_GUARD_PROMPT = """The active skill is read-only Polymarket research. The expected tools
(market search, web search, and general read-only helpers — a calculator, the current
date/time, and fetching a page) are all read-only. Allow them freely; this skill performs
no trading or money-moving actions.
"""

_RESPONDER_PROMPT = """You are finalizing a Polymarket research turn.

Read the conversation above (the analysis and the tool results) and produce the result:
- `summary`: a short natural-language answer. If no market is worth suggesting, say so
  here and leave `suggestions` empty.
- `suggestions`: a ranked shortlist (up to 5). Each suggestion needs a risk assessment.

Hard rules:
- ONLY include markets whose `market_id` actually appears in the polymarket tool results.
  Never invent a market or an id.
- Use the markets' real `url` and `implied_probability` from the tool results.
- Keep rationales grounded in the evidence gathered, not generic.
"""


def find_skill(polymarket_search: BaseTool, web_search: BaseTool) -> Skill:
    return Skill(
        name="find",
        triggers=("find",),
        description="Discover and rank a shortlist of interesting Polymarket bets on a topic or theme, each with a risk assessment.",
        planner_prompt=_PLANNER_PROMPT,
        guard_prompt=_GUARD_PROMPT,
        responder_prompt=_RESPONDER_PROMPT,
        output_schema=ResearchResult,
        tools=(polymarket_search, web_search),
    )
