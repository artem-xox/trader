"""Shared pieces of the app's Server-Sent Events surface.

Phase 1 moves the agent's SSE generator here so the web and Telegram endpoints
share one implementation (docs/WEB.md §5.3). For now it owns the response
headers, which every streaming endpoint must send.
"""

from __future__ import annotations

# Buffering is the one thing that breaks SSE without breaking anything else: the
# run still succeeds, the frames just all arrive at the end. `no-cache` and
# `X-Accel-Buffering` are the two hints proxies actually honour — App Platform's
# edge cache is the documented reason SSE arrives as a single chunk, and it does
# not cache POST responses, which is why every stream here is a POST.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
