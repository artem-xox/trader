from __future__ import annotations

from trader.common.config import Settings, get_settings


class BaseAgent:
    """Common base: holds settings. The agent interface is `models.protocols.Agent`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
