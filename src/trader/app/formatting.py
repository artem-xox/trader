"""Render a structured ResearchResult into human-readable markdown for chat clients."""

from __future__ import annotations

from trader.core.models.domain import ResearchResult


def format_result(result: ResearchResult) -> str:
    lines = [result.summary]
    for i, s in enumerate(result.suggestions, 1):
        prob = f"{s.implied_probability:.0%}" if s.implied_probability is not None else "n/a"
        header = f"\n*{i}. {s.question}*"
        if s.url:
            header = f"\n*{i}. [{s.question}]({s.url})*"
        lines.append(header)
        lines.append(f"Implied: {prob} · confidence: {s.confidence} · risk: {s.risk.level}")
        lines.append(s.rationale)
        if s.risk.note:
            lines.append(f"_Risk: {s.risk.note}_")
    return "\n".join(lines)
