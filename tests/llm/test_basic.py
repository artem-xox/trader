"""Basic LLM smoke test — the agent runs end-to-end and returns a structured result."""

from __future__ import annotations


async def test_returns_grounded_answer(invoke_prompt):
    """An off-domain prompt still yields a coherent summary and no invented markets.

    The agent always synthesizes a `ResearchResult`; with no market context it must
    answer in the summary and leave `suggestions` empty (anti-hallucination holds).
    """
    result = await invoke_prompt("Reply with exactly the single word: pong")
    assert result.summary.strip()
    assert result.suggestions == []
