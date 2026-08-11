"""The app's Server-Sent Events surface, shared by both streaming endpoints.

`/agent/stream` (Telegram) and `/api/conversations/{id}/turns` (web) run the same
turn the same way; only what they do with the terminal event differs. That run —
including the three tracing modes `/agent/invoke` mirrors — lives here once.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import nullcontext

from langchain_core.messages import HumanMessage
from langchain_core.tracers.context import tracing_v2_enabled
from langsmith import trace, tracing_context

from trader.app.formatting import format_result
from trader.app.schemas import StreamEvent
from trader.common.config import get_settings
from trader.core.models.protocols import Agent

logger = logging.getLogger(__name__)

# Buffering is the one thing that breaks SSE without breaking anything else: the run
# still succeeds, the frames just all arrive at the end. `no-cache` and
# `X-Accel-Buffering` are the two hints proxies actually honour — App Platform's edge
# cache is the documented reason SSE arrives as a single chunk, and it does not cache
# POST responses, which is why every stream here is a POST.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def frame(event: StreamEvent) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


def safe_trace_url(get_url: Callable[[], str] | None) -> str | None:
    """Best-effort LangSmith URL; resolving it must never fail the request."""
    if get_url is None:
        return None
    try:
        return get_url()
    except Exception:  # noqa: BLE001
        logger.exception("could not resolve LangSmith trace URL")
        return None


async def _emit(
    agent: Agent,
    message: str,
    thread_id: str | None,
    *,
    get_url: Callable[[], str] | None = None,
    run=None,
    suppress: bool = False,
) -> AsyncIterator[StreamEvent]:
    """Turn the agent's progress events into stream events; `final` carries the answer.

    `suppress` mutes nested tracing (compressed mode); `run`/`get_url` attach the trace.
    """
    with tracing_context(enabled=False) if suppress else nullcontext():
        async for event in agent.astream([HumanMessage(message)], thread_id=thread_id):
            if event.kind != "final":
                yield StreamEvent(kind="status", label=event.label, detail=event.detail)
                continue
            response = format_result(event.result) if event.result is not None else ""
            if run is not None:
                run.add_outputs({"response": response})
            yield StreamEvent(
                kind="final",
                response=response,
                result=event.result,
                trace_url=safe_trace_url(get_url),
            )


async def agent_events(
    agent: Agent, message: str, *, thread_id: str | None, debug: bool = False
) -> AsyncIterator[StreamEvent]:
    """Run one turn, yielding status events and then exactly one `final` or `error`.

    Tracing mirrors `/agent/invoke`: no key → off; `debug` → the full nested trace and
    its URL; otherwise → one compressed root span with nested tracing suppressed.
    """
    settings = get_settings()
    try:
        if not settings.langsmith_api_key:
            async for event in _emit(agent, message, thread_id):
                yield event
        elif debug:
            with tracing_v2_enabled(project_name=settings.langsmith_project) as cb:
                async for event in _emit(agent, message, thread_id, get_url=cb.get_run_url):
                    yield event
        else:
            with tracing_context(enabled=True), trace(
                name="agent.stream",
                project_name=settings.langsmith_project,
                inputs={"message": message, "thread_id": thread_id},
            ) as run:
                async for event in _emit(
                    agent, message, thread_id, get_url=run.get_url, run=run, suppress=True
                ):
                    yield event
    except Exception:  # noqa: BLE001 - surface a single error event, log details
        logger.exception("agent stream failed")
        yield StreamEvent(kind="error")
