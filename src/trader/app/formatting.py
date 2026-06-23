"""Render a structured result into human-readable markdown for chat clients."""

from __future__ import annotations

from trader.core.models.domain import MarketAnalysis, ResearchResult, SkillResult


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "n/a"


def format_result(result: SkillResult) -> str:
    if isinstance(result, ResearchResult):
        return _format_research(result)
    if isinstance(result, MarketAnalysis):
        return _format_analysis(result)
    return result.summary


def _format_research(result: ResearchResult) -> str:
    lines = [result.summary]
    for i, s in enumerate(result.suggestions, 1):
        header = f"\n*{i}. [{s.question}]({s.url})*" if s.url else f"\n*{i}. {s.question}*"
        lines.append(header)
        lines.append(f"Implied: {_pct(s.implied_probability)} · confidence: {s.confidence} · risk: {s.risk.level}")
        lines.append(s.rationale)
        if s.risk.note:
            lines.append(f"_Risk: {s.risk.note}_")
    return "\n".join(lines)


def _format_analysis(a: MarketAnalysis) -> str:
    title = f"*[{a.question}]({a.url})*" if a.url else f"*{a.question}*"
    lines = [
        a.summary,
        f"\n{title}",
        f"Implied: {_pct(a.implied_probability)} · fair: {_pct(a.fair_probability)} "
        f"· stance: {a.stance} · confidence: {a.confidence}",
        f"Edge: {a.edge}",
    ]
    if a.key_factors:
        lines.append("Key factors: " + "; ".join(a.key_factors))
    lines.append(f"_Risk ({a.risk.level}): {a.risk.note}_")
    return "\n".join(lines)
