"""FastAPI application that serves the trading agent.

The agent is instantiated once at startup and reused across requests. The bot (or any
client) calls `POST /agent/invoke` to run the ReAct loop.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, nullcontext

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from langchain_core.messages import HumanMessage
from langchain_core.tracers.context import tracing_v2_enabled
from langsmith import trace, tracing_context

from trader.app.formatting import format_result
from trader.app.schemas import InvokeRequest, InvokeResponse, StreamEvent
from trader.common.config import get_settings
from trader.core.bootstrap import build_agent
from trader.core.models.domain import SkillResult
from trader.core.models.protocols import Agent

load_dotenv()  # so LANGSMITH_* and other vars are present for LangChain tracing

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    expected = get_settings().agent_api_key
    if not expected:
        return  # dev mode: no key configured, allow all
    if key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    logger.info("Agent initialized")
    yield


app = FastAPI(title="AI Trader — Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _safe_url(get_url: Callable[[], str]) -> str | None:
    """Best-effort LangSmith URL; resolving it must never fail the request."""
    try:
        return get_url()
    except Exception:  # noqa: BLE001
        logger.exception("could not resolve LangSmith trace URL")
        return None


@app.post("/agent/invoke", response_model=InvokeResponse, dependencies=[Depends(_require_api_key)])
async def invoke(req: InvokeRequest) -> InvokeResponse:
    agent: Agent = app.state.agent
    settings = get_settings()
    messages = [HumanMessage(req.message)]

    # Without an API key there's nowhere to upload — just run the agent.
    if not settings.langsmith_api_key:
        result = await agent.invoke(messages, thread_id=req.thread_id)
        return InvokeResponse(response=format_result(result), result=result)

    # Debug (Telegram /debug, or `debug: true` on the API) → full nested trace: every graph
    # node, LLM call and tool call shows up, and we hand back the trace URL.
    if req.debug:
        with tracing_v2_enabled(project_name=settings.langsmith_project) as cb:
            result: SkillResult = await agent.invoke(messages, thread_id=req.thread_id)
            trace_url = _safe_url(cb.get_run_url)
        return InvokeResponse(response=format_result(result), result=result, trace_url=trace_url)

    # Otherwise → always trace, but compressed to a single span: an explicit root run carries
    # the turn's input/output while the agent runs with nested tracing suppressed, so routine
    # traffic is observable without the full graph hanging under every run.
    with tracing_context(enabled=True), trace(
        name="agent.invoke",
        project_name=settings.langsmith_project,
        inputs={"message": req.message, "thread_id": req.thread_id},
    ) as run:
        with tracing_context(enabled=False):
            result = await agent.invoke(messages, thread_id=req.thread_id)
        response = format_result(result)
        run.add_outputs({"response": response})
    return InvokeResponse(response=response, result=result, trace_url=_safe_url(run.get_url))


def _frame(event: StreamEvent) -> str:
    return f"data: {event.model_dump_json(exclude_none=True)}\n\n"


async def _emit(
    agent: Agent,
    messages: list[HumanMessage],
    thread_id: str | None,
    *,
    get_url: Callable[[], str] | None = None,
    run=None,
    suppress: bool = False,
) -> AsyncIterator[str]:
    """Turn the agent's progress events into SSE frames; the `final` one carries the answer.

    `suppress` mutes nested tracing (compressed mode); `run`/`get_url` attach the trace.
    """
    with tracing_context(enabled=False) if suppress else nullcontext():
        async for event in agent.astream(messages, thread_id=thread_id):
            if event.kind != "final":
                yield _frame(StreamEvent(kind="status", label=event.label, detail=event.detail))
                continue
            response = format_result(event.result) if event.result is not None else ""
            if run is not None:
                run.add_outputs({"response": response})
            yield _frame(
                StreamEvent(
                    kind="final",
                    response=response,
                    result=event.result,
                    trace_url=_safe_url(get_url) if get_url is not None else None,
                )
            )


async def _agent_sse(req: InvokeRequest) -> AsyncIterator[str]:
    """Stream the agent run as SSE, mirroring /invoke's three tracing modes."""
    agent: Agent = app.state.agent
    settings = get_settings()
    messages = [HumanMessage(req.message)]
    try:
        if not settings.langsmith_api_key:
            async for frame in _emit(agent, messages, req.thread_id):
                yield frame
        elif req.debug:
            with tracing_v2_enabled(project_name=settings.langsmith_project) as cb:
                async for frame in _emit(agent, messages, req.thread_id, get_url=cb.get_run_url):
                    yield frame
        else:
            with tracing_context(enabled=True), trace(
                name="agent.stream",
                project_name=settings.langsmith_project,
                inputs={"message": req.message, "thread_id": req.thread_id},
            ) as run:
                async for frame in _emit(
                    agent, messages, req.thread_id, get_url=run.get_url, run=run, suppress=True
                ):
                    yield frame
    except Exception:  # noqa: BLE001 - surface a single error frame, log details
        logger.exception("agent stream failed")
        yield _frame(StreamEvent(kind="error"))


@app.post("/agent/stream", dependencies=[Depends(_require_api_key)])
async def stream(req: InvokeRequest) -> StreamingResponse:
    return StreamingResponse(_agent_sse(req), media_type="text/event-stream")
