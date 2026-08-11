"""FastAPI application that serves the trading agent.

The agent is instantiated once at startup and reused across requests. The bot (or any
client) calls `POST /agent/invoke` to run the ReAct loop.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langchain_core.tracers.context import tracing_v2_enabled
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langsmith import trace, tracing_context
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from trader.app import conversations, probe
from trader.app.formatting import format_result
from trader.app.schemas import InvokeRequest, InvokeResponse
from trader.app.security import require_api_key
from trader.app.store import Store
from trader.app.streaming import SSE_HEADERS, agent_events, frame, safe_trace_url
from trader.common.config import get_settings
from trader.core.bootstrap import build_agent
from trader.core.models.domain import SkillResult
from trader.core.models.protocols import Agent

load_dotenv()  # so LANGSMITH_* and other vars are present for LangChain tracing

logger = logging.getLogger(__name__)

async def _open_persistence(dsn: str) -> tuple[Store, AsyncPostgresSaver, AsyncConnectionPool]:
    """Open both pools and apply both schemas: ours and the checkpointer's."""
    checkpointer_pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=3,
        open=False,
        # What LangGraph's Postgres checkpointer requires of its connections.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await checkpointer_pool.open(wait=True)
    try:
        checkpointer = AsyncPostgresSaver(checkpointer_pool)
        await checkpointer.setup()
        store = await Store.connect(dsn)
    except Exception:
        await checkpointer_pool.close()
        raise
    return store, checkpointer, checkpointer_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wire persistence, then the agent.

    With a reachable DATABASE_URL, conversations and the agent's per-thread memory both
    live in Postgres and survive a restart.

    Without one — unset, or unreachable — the app runs entirely in memory instead of
    refusing to start: the agent still answers, Telegram still works, and only the
    conversation endpoints are down (503). A crash here is worse than a degraded start,
    because it takes the whole service with it and App Platform then rolls the release
    back. `GET /api/health` reports which mode is live, so "degraded" cannot pass for
    "fine".
    """
    settings = get_settings()
    # In-flight turns outlive their requests (see conversations.create_turn), so the app
    # holds the references that keep them from being garbage-collected.
    app.state.turns = set()
    app.state.store = None
    app.state.checkpointer = None
    pool = None

    if not settings.database_url:
        logger.warning("DATABASE_URL is unset — conversations disabled, agent memory in-process")
    else:
        try:
            app.state.store, app.state.checkpointer, pool = await _open_persistence(
                settings.database_url
            )
            logger.info("Agent initialized with Postgres persistence")
        except Exception:  # noqa: BLE001 - degrade rather than fail the whole service
            logger.exception("Postgres unavailable — conversations disabled, memory in-process")

    app.state.agent = build_agent(checkpointer=app.state.checkpointer)
    try:
        yield
    finally:
        if app.state.store is not None:
            await app.state.store.close()
        if pool is not None:
            await pool.close()


app = FastAPI(title="AI Trader — Agent", lifespan=lifespan)
app.include_router(probe.router)
app.include_router(conversations.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/invoke", response_model=InvokeResponse, dependencies=[Depends(require_api_key)])
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
            trace_url = safe_trace_url(cb.get_run_url)
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
    return InvokeResponse(response=response, result=result, trace_url=safe_trace_url(run.get_url))


async def _agent_sse(req: InvokeRequest) -> AsyncIterator[str]:
    async for event in agent_events(
        app.state.agent, req.message, thread_id=req.thread_id, debug=req.debug
    ):
        yield frame(event)


@app.post("/agent/stream", dependencies=[Depends(require_api_key)])
async def stream(req: InvokeRequest) -> StreamingResponse:
    return StreamingResponse(
        _agent_sse(req), media_type="text/event-stream", headers=SSE_HEADERS
    )


# The SPA, last: routes registered above win, so the API keeps its paths and
# everything else falls through to the build. Mounted only when the directory
# exists, so `make app` runs without a prior `npm run build` — in the image the
# Dockerfile's web stage always puts it there.
_web_dist = Path(get_settings().web_dist_dir)
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=_web_dist, html=True), name="web")
else:
    logger.info("web build not found at %s — serving API only", _web_dist)
