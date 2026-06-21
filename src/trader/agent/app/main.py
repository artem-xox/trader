"""FastAPI application that serves the trading agent.

The agent is instantiated once at startup and reused across requests. The bot (or any
client) calls `POST /agent/invoke` to run the ReAct loop.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from trader.agent.app.schemas import InvokeRequest, InvokeResponse
from trader.agent.core.agent import TradingAgent

load_dotenv()  # so LANGSMITH_* and other vars are present for LangChain tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = TradingAgent()
    logger.info("TradingAgent initialized")
    yield


app = FastAPI(title="AI Trader — Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/invoke", response_model=InvokeResponse)
async def invoke(req: InvokeRequest) -> InvokeResponse:
    agent: TradingAgent = app.state.agent
    answer = await agent.run(req.message)
    return InvokeResponse(response=answer)
