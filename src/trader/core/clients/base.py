"""Shared HTTP plumbing for REST API clients.

Concrete clients (Gamma, CLOB) inherit this and keep only their endpoints, request
params, and response processing — the transport (timeouts, one-shot connections,
status handling) lives here once.
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(15.0)


class BaseHttpClient:
    def __init__(self, base_url: str, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET `base_url + path` and return the decoded JSON body.

        Raises `httpx.HTTPError` on transport failures and non-2xx responses; callers
        decide how to surface that (agent tools return an error string the model can
        react to).
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
