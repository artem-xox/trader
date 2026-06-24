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
1. Use `polymarket_search` to find real, active markets on the topic.
2. Use `web_search` to gather current news and facts, so you can judge whether a market's
   implied probability looks mispriced (the edge).
3. Evaluate candidates on: relevance, implied probability vs. your read of reality (edge),
   liquidity/volume, and time horizon.

Never invent markets — only reason about markets returned by the tools.
"""

_GUARD_PROMPT = """The active skill is read-only Polymarket research. The only expected
tools are market search and web search — both read-only. Allow them freely; this skill
performs no trading or money-moving actions.
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
