"""Basic LLM smoke test — normal mode answers a simple instruction end-to-end."""

from __future__ import annotations

from trader.core.models.domain import GeneralAnswer


async def test_normal_mode_follows_instruction(invoke_prompt):
    """No skill applies → normal mode returns a plain GeneralAnswer echoing the reply."""
    result = await invoke_prompt("Reply with exactly the single word: pong")
    assert isinstance(result, GeneralAnswer)
    assert "pong" in result.summary.lower()
