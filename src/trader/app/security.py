"""The shared-secret gate in front of everything the browser and the bot call.

Lives apart from `main` so routers can depend on it without importing the app.
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from trader.common.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_api_key_header)) -> None:
    expected = get_settings().agent_api_key
    if not expected:
        return  # dev mode: no key configured, allow all
    if key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
