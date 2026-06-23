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

from trader.app.formatting import format_result
from trader.app.schemas import InvokeRequest, InvokeResponse
from trader.common.config import get_settings
from trader.core.bootstrap import build_agent
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
    result = await agent.invoke([HumanMessage(req.message)], thread_id=req.thread_id)
    return InvokeResponse(response=format_result(result), result=result)
