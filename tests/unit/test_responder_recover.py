"""Offline tests for the responder's tolerant JSON recovery.

Strict structured output normally guarantees clean JSON, but the model occasionally appends
a prose tail after the object; `_recover` salvages the turn instead of crashing it.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from trader.core.components.responder import _recover
from trader.core.models.domain import GeneralAnswer, MarketAnalysis


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


def test_recover_raises_on_no_json():
    with pytest.raises(ValueError):
        _recover(AIMessage("not json at all"), GeneralAnswer)
