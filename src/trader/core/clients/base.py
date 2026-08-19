"""Shared HTTP plumbing for REST API clients.

Concrete clients (Gamma, CLOB) inherit this and keep only their endpoints, request
params, and response processing — the transport (timeouts, one-shot connections,
status handling) lives here once.
"""

from __future__ import annotations

from typing import Any

import httpx
from langsmith import trace

DEFAULT_TIMEOUT = httpx.Timeout(15.0)


class BaseHttpClient:
    def __init__(self, base_url: str, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET `base_url + path` and return the decoded JSON body.

        Raises `httpx.HTTPError` on transport failures and non-2xx responses; callers
        decide how to surface that (agent tools return an error string the model can
        react to). Traced via LangSmith so request params, response body, and status
        code show up in the same project as the agent's own runs; follows the ambient
        tracing_context, so it's suppressed/included exactly like everything else.
        """
        async with trace(
            name=f"GET {path}",
            run_type="tool",
            inputs={"base_url": self._base_url, "path": path, "params": params},
        ) as run:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}{path}", params=params)
                run.add_outputs({"status_code": resp.status_code})
                resp.raise_for_status()
                body = resp.json()
            run.add_outputs({"status_code": resp.status_code, "body": body})
            return body
