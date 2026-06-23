"""Basic LLM smoke tests — the model responds and follows simple instructions."""

from __future__ import annotations


async def test_simple_arithmetic(invoke_prompt):
    out = await invoke_prompt("What is 2 + 2? Reply with just the number.")
    assert "4" in out


async def test_follows_instruction(invoke_prompt):
    out = await invoke_prompt("Reply with exactly the single word: pong")
    assert "pong" in out.lower()
