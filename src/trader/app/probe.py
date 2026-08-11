"""Diagnostics the browser can run against a deployed app.

Both endpoints exist to verify the delivery path, not the agent: that the API
answers under `/api` now that FastAPI also serves the SPA, and that SSE frames
reach the browser one at a time instead of in one buffered chunk. They cost
nothing to keep and are the fastest way to tell whether a deployment problem is
the agent or the platform.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from trader.app.streaming import SSE_HEADERS

router = APIRouter(prefix="/api", tags=["probe"])

# Enough frames, spaced widely enough, that a buffered response is unmistakable
# when the client compares arrival times.
_PROBE_FRAMES = 5
_PROBE_INTERVAL_S = 1.0


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Liveness, reachable on the path the browser actually uses.

    Also reports whether persistence came up. The app deliberately starts without
    Postgres rather than crash-looping (see the lifespan), so without this a degraded
    deployment would look identical to a healthy one from the outside.

    `/health` (no prefix) stays as it is — that one is the App Platform health check
    and must not move.
    """
    return {
        "status": "ok",
        "storage": "postgres" if request.app.state.store is not None else "unavailable",
    }


async def _probe_frames() -> AsyncIterator[str]:
    for seq in range(_PROBE_FRAMES):
        payload = {"seq": seq, "total": _PROBE_FRAMES, "sent_at": time.time()}
        yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(_PROBE_INTERVAL_S)


@router.post("/stream-probe")
async def stream_probe() -> StreamingResponse:
    """Emit a fixed number of SSE frames a second apart.

    POST rather than GET on purpose: it mirrors how the agent streams, and the
    two are not equivalent at the edge — POST responses are not edge-cached, so
    a GET probe could fail while the path we actually ship works.
    """
    return StreamingResponse(_probe_frames(), media_type="text/event-stream", headers=SSE_HEADERS)
