"""FastAPI application that serves the trading agent.

The agent is instantiated once at startup and reused across requests. The bot (or any
client) calls `POST /agent/invoke` to run the ReAct loop.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from langchain_core.messages import HumanMessage

from trader.app.schemas import InvokeRequest, InvokeResponse
from trader.core.bootstrap import build_agent
from trader.core.models.protocols import Agent

load_dotenv()  # so LANGSMITH_* and other vars are present for LangChain tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    logger.info("Agent initialized")
    yield


app = FastAPI(title="AI Trader — Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/invoke", response_model=InvokeResponse)
async def invoke(req: InvokeRequest) -> InvokeResponse:
    agent: Agent = app.state.agent
    # TODO: once the UI has storage, pass the full conversation history here.
    answer = await agent.invoke([HumanMessage(req.message)])
    return InvokeResponse(response=answer)
