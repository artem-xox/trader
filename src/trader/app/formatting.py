"""Render a structured result into human-readable markdown for chat clients.

The markdown here is plain CommonMark (`**bold**`, `[text](url)`, `_italic_`); the client
turns it into its own dialect (the Telegram bot runs it through `telegramify_markdown`).
"""

from __future__ import annotations

from trader.core.models.domain import Level, MarketAnalysis, ResearchResult, SkillResult, Stance

# Directional call → (emoji, label). Risk/confidence reuse a shared traffic-light scale.
_STANCE = {
    Stance.LEAN_YES: ("📈", "Lean YES"),
    Stance.LEAN_NO: ("📉", "Lean NO"),
    Stance.PASS: ("⏸", "Pass"),
}
_LIGHT = {Level.LOW: "🟢", Level.MEDIUM: "🟡", Level.HIGH: "🔴"}


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "n/a"


def _link(text: str, url: str | None) -> str:
    return f"[{text}]({url})" if url else text


def _odds(implied: float | None, fair: float | None) -> str | None:
    """One line contrasting market price with the analyst's fair estimate."""
    if implied is None and fair is None:
        return None
    if fair is None:
        return f"💰 Implied {_pct(implied)}"
    return f"💰 Implied {_pct(implied)} → fair {_pct(fair)}"


def format_result(result: SkillResult) -> str:
    if isinstance(result, ResearchResult):
        return _format_research(result)
    if isinstance(result, MarketAnalysis):
        return _format_analysis(result)
    return result.summary


def _format_analysis(a: MarketAnalysis) -> str:
    emoji, label = _STANCE.get(a.stance, ("", a.stance))
    blocks = [
        a.summary,
        f"📊 **{_link(a.question, a.url)}**\n"
        f"{emoji} **{label}** · 🎯 confidence {a.confidence}",
    ]
    if odds := _odds(a.implied_probability, a.fair_probability):
        blocks[-1] += f"\n{odds}"
    blocks.append(f"💡 **Edge**\n{a.edge}")
    if a.key_factors:
        factors = "\n".join(f"• {f}" for f in a.key_factors)
        blocks.append(f"🔑 **Key factors**\n{factors}")
    blocks.append(f"{_LIGHT.get(a.risk.level, '⚠️')} **Risk: {a.risk.level}**\n{a.risk.note}")
    return "\n\n".join(blocks)


def _format_research(r: ResearchResult) -> str:
    blocks = [r.summary]
    for i, s in enumerate(r.suggestions, 1):
        lines = [
            f"**{i}. {_link(s.question, s.url)}**",
            f"💰 implied {_pct(s.implied_probability)} · 🎯 confidence {s.confidence} "
            f"· {_LIGHT.get(s.risk.level, '⚠️')} risk {s.risk.level}",
            s.rationale,
        ]
        if s.risk.note:
            lines.append(f"_{s.risk.note}_")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
