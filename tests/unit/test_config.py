"""Settings parsing — specifically the chat allowlist, which is read from the
environment and used to crash the Telegram worker at import.

The trap: for a list-typed field pydantic-settings JSON-decodes the raw value
inside the settings *source*, before any validator runs. So the comma-separated
form documented in .env.template never reached the validator, and an empty string
— what a DigitalOcean env var with no value becomes — raised a bare
JSONDecodeError during startup. `NoDecode` on the field is what makes these pass.
"""

from __future__ import annotations

import pytest

from trader.common.config import Settings


def _chat_ids(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> list[int]:
    if raw is None:
        monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", raw)
    # `_env_file=None` keeps a developer's own .env out of the assertion.
    return Settings(_env_file=None).telegram_allowed_chat_ids


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),  # unset
        ("", []),  # what the app spec sets, and what took the worker down
        ("123456", [123456]),
        ("123456,789012", [123456, 789012]),  # the documented form
        (" 123456 , 789012 ", [123456, 789012]),
        ("[123456,789012]", [123456, 789012]),  # the only form that worked before
    ],
)
def test_allowed_chat_ids_accepts_every_documented_form(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: list[int]
) -> None:
    assert _chat_ids(monkeypatch, raw) == expected


def test_allowed_chat_ids_rejects_nonsense(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _chat_ids(monkeypatch, "not-an-id")
