"""FastAPI application that serves the trading agent.

The agent is instantiated once at startup and reused across requests. The bot (or any
client) calls `POST /agent/invoke` to run the ReAct loop.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from langchain_core.messages import HumanMessage
from langchain_core.tracers.context import tracing_v2_enabled
from langsmith import tracing_context

from trader.app.formatting import format_result
from trader.app.schemas import InvokeRequest, InvokeResponse
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


@app.post("/agent/invoke", response_model=InvokeResponse, dependencies=[Depends(_require_api_key)])
async def invoke(req: InvokeRequest) -> InvokeResponse:
    agent: Agent = app.state.agent
    settings = get_settings()
    messages = [HumanMessage(req.message)]

    # Tracing is opt-in per turn. Only a debug request (Telegram /debug, or `debug: true` on
    # the API) ships a trace to LangSmith and hands back its URL; the tracer is installed via
    # context, so the agent picks it up without any changes to its config. A configured API
    # key is the one prerequisite — without it there is nowhere to upload.
    if req.debug and settings.langsmith_api_key:
        with tracing_v2_enabled(project_name=settings.langsmith_project) as cb:
            result: SkillResult = await agent.invoke(messages, thread_id=req.thread_id)
            try:
                trace_url: str | None = cb.get_run_url()
            except Exception:  # noqa: BLE001 - trace URL is best-effort, never fail the request
                logger.exception("could not resolve LangSmith trace URL")
                trace_url = None
        return InvokeResponse(response=format_result(result), result=result, trace_url=trace_url)

    # Every non-debug turn runs with tracing forced off, so routine traffic never ships a
    # trace even if LANGSMITH_TRACING is left enabled globally.
    with tracing_context(enabled=False):
        result = await agent.invoke(messages, thread_id=req.thread_id)
    return InvokeResponse(response=format_result(result), result=result)
