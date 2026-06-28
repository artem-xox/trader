"""Offline tests for chat-facing result formatting."""

from __future__ import annotations

from trader.app.formatting import format_result
from trader.core.models.domain import (
    GeneralAnswer,
    Level,
    MarketAnalysis,
    ResearchResult,
    RiskAssessment,
    Stance,
    Suggestion,
)
from trader.ui.telegram.main import _to_markdown_v2


def _analysis(**kw) -> MarketAnalysis:
    base = dict(
        summary="s",
        market_id="m",
        question="Will BTC dip to $57,500?",
        url="https://polymarket.com/x",
        implied_probability=0.42,
        fair_probability=0.45,
        edge="A brief touch of $57,500 is likely.",
        stance=Stance.LEAN_YES,
        confidence=Level.MEDIUM,
        key_factors=["price near $59,000 strike", "implied below fair"],
        risk=RiskAssessment(level=Level.MEDIUM, factors=[], note="sideways favours no"),
    )
    base.update(kw)
    return MarketAnalysis(**base)


def test_general_answer_is_plain_summary():
    assert format_result(GeneralAnswer(summary="just this")) == "just this"


def test_analysis_has_stance_factors_and_risk_light():
    out = format_result(_analysis())
    assert "📈 **Lean YES**" in out
    assert "💡 **Edge**" in out
    assert "• price near $59,000 strike" in out  # factors as bullets, not "; "-joined
    assert "🟡 **Risk: medium**" in out
    assert "💰 Implied 42% → fair 45%" in out


def test_analysis_odds_line_omitted_when_unknown():
    out = format_result(_analysis(implied_probability=None, fair_probability=None))
    assert "💰" not in out


def test_research_lists_numbered_bold_links_with_risk_light():
    r = ResearchResult(
        summary="one idea",
        suggestions=[
            Suggestion(
                market_id="1",
                question="A?",
                url="https://p/x",
                implied_probability=0.3,
                rationale="why a",
                confidence=Level.LOW,
                risk=RiskAssessment(level=Level.HIGH, factors=[], note="risky"),
            )
        ],
    )
    out = format_result(r)
    assert "**1. [A?](https://p/x)**" in out
    assert "🔴 risk high" in out
    assert "_risky_" in out


def test_dollar_prices_survive_telegram_conversion():
    # Regression: telegramify reads `$…$` as LaTeX and renders the span monospace; the bot
    # escapes `$` so prices stay literal text and never collapse into a code span.
    v2 = _to_markdown_v2(format_result(_analysis()))
    assert "`" not in v2  # no stray inline-code span
    assert "$57,500" in v2  # price stays literal
