"""Tavily web search client."""

from __future__ import annotations

import json

from tavily import AsyncTavilyClient


class TavilyClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncTavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 5) -> str:
        try:
            resp = await self._client.search(
                query,
                max_results=max(1, min(max_results, 10)),
                search_depth="basic",
                include_answer=True,
            )
        except Exception as exc:  # noqa: BLE001 - return a tool error the model can handle
            return f"Web search failed: {exc}"

        results = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "published_date": r.get("published_date"),
                "snippet": r.get("content"),
            }
            for r in resp.get("results", [])
        ]
        if not results:
            return f"No web results found for query: {query!r}."
        return json.dumps(
            {"answer": resp.get("answer"), "results": results}, ensure_ascii=False
        )
