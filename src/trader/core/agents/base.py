from __future__ import annotations

from trader.common.config import Settings, get_settings

class BaseAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def invoke(self, message: str) -> str:
        raise NotImplementedError("Subclasses must implement this method")