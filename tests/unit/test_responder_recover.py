"""Offline tests for the responder's tolerant JSON recovery.

Function-calling normally returns clean tool-call args, but the model can occasionally
answer in prose or wrap the JSON in text; `_recover` salvages the turn instead of crashing.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from trader.core.components.responder import _recover
from trader.core.models.domain import GeneralAnswer, MarketAnalysis


def test_recover_prefers_tool_call_args():
    raw = AIMessage(
        content="",
        tool_calls=[{"name": "GeneralAnswer", "args": {"summary": "from-tool"}, "id": "1"}],
    )
    assert _recover(raw, GeneralAnswer).summary == "from-tool"


def test_recover_ignores_trailing_prose():
    raw = AIMessage('{"summary": "hello"}\nSome trailing prose that broke the parser.')
    assert _recover(raw, GeneralAnswer).summary == "hello"


def test_recover_handles_leading_whitespace():
    raw = AIMessage('   \n{"summary": "ok"}\n\nmore text')
    assert _recover(raw, GeneralAnswer).summary == "ok"


def test_recover_validates_against_schema():
    raw = AIMessage(
        '{"summary": "s", "market_id": "1", "question": "q?", "edge": "e", '
        '"stance": "pass", "confidence": "low", '
        '"risk": {"level": "low", "note": "n"}}\ntrailing'
    )
    result = _recover(raw, MarketAnalysis)
    assert result.market_id == "1"
    assert result.stance.value == "pass"


def test_recover_falls_back_to_prose_summary():
    # No tool call and no JSON: keep the prose as the answer instead of crashing.
    raw = AIMessage("The latest iOS is 18, with better battery life.")
    assert _recover(raw, GeneralAnswer).summary == "The latest iOS is 18, with better battery life."


def test_recover_finds_json_after_prose():
    raw = AIMessage('Here is the answer:\n{"summary": "ok"}')
    assert _recover(raw, GeneralAnswer).summary == "ok"


def test_recover_empty_content_does_not_crash():
    assert _recover(AIMessage(""), GeneralAnswer).summary == "(no answer produced)"
