"""The web client's conversation API (docs/WEB.md §5.1).

The turn endpoint is the only write path: it records the user's message, runs the
agent with `thread_id` = the conversation id, streams progress, and records the
answer. The transcript is written by the server rather than the client, so closing
the tab mid-run loses the live progress but never the answer.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from trader.app.schemas import (
    Conversation,
    ConversationDetail,
    StreamEvent,
    TitleUpdate,
    TurnRequest,
)
from trader.app.security import require_api_key
from trader.app.store import Store, title_from
from trader.app.streaming import SSE_HEADERS, agent_events, frame
from trader.core.models.protocols import Agent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations", tags=["conversations"], dependencies=[Depends(require_api_key)]
)


def get_store(request: Request) -> Store:
    """The store is absent when DATABASE_URL is unset *or* when Postgres could not be
    reached at startup: the app degrades instead of refusing to boot, so the agent
    still answers and only conversations are down. Which of the two it was is in the
    startup log; `GET /api/health` reports that storage is off either way."""
    store: Store | None = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation storage is unavailable — the agent is running without it",
        )
    return store


async def _load(store: Store, conversation_id: UUID) -> Conversation:
    conversation = await store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such conversation")
    return conversation


@router.get("", response_model=list[Conversation])
async def list_conversations(store: Store = Depends(get_store)) -> list[Conversation]:
    return await store.list_conversations()


@router.post("", response_model=Conversation, status_code=status.HTTP_201_CREATED)
async def create_conversation(store: Store = Depends(get_store)) -> Conversation:
    """Untitled: the first turn renames it after the message that starts it."""
    return await store.create_conversation()


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, store: Store = Depends(get_store)
) -> ConversationDetail:
    conversation = await _load(store, conversation_id)
    messages = await store.get_messages(conversation_id)
    return ConversationDetail(**conversation.model_dump(), messages=messages)


@router.patch("/{conversation_id}", response_model=Conversation)
async def rename_conversation(
    conversation_id: UUID, update: TitleUpdate, store: Store = Depends(get_store)
) -> Conversation:
    await _load(store, conversation_id)
    await store.rename_conversation(conversation_id, update.title)
    return await _load(store, conversation_id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, request: Request, store: Store = Depends(get_store)
) -> Response:
    await _load(store, conversation_id)
    await store.delete_conversation(conversation_id)
    # Messages cascade, but the agent's own memory for this thread lives in the
    # checkpointer's tables and would otherwise outlive the conversation that owned it.
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is not None:
        await checkpointer.adelete_thread(str(conversation_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _run_turn(
    agent: Agent,
    store: Store,
    conversation_id: UUID,
    turn: TurnRequest,
    queue: asyncio.Queue[StreamEvent | None],
) -> None:
    """Run the turn to completion, persisting the answer, and publish every event.

    Deliberately not tied to the request: it runs as its own task, so a browser that
    navigates away mid-run still gets its answer written to the transcript. Nothing
    reconnects to a run in progress — reopening the conversation shows the answer once
    it lands.
    """
    try:
        async for event in agent_events(
            agent, turn.message, thread_id=str(conversation_id), debug=turn.debug
        ):
            if event.kind == "final":
                await store.add_message(
                    conversation_id,
                    "assistant",
                    event.response or "",
                    result=event.result.model_dump(mode="json") if event.result else None,
                    trace_url=event.trace_url,
                )
            await queue.put(event)
    except Exception:  # noqa: BLE001 - the request may already be gone; log and end cleanly
        logger.exception("turn failed for conversation %s", conversation_id)
        await queue.put(StreamEvent(kind="error"))
    finally:
        await queue.put(None)


async def _drain(queue: asyncio.Queue[StreamEvent | None]) -> AsyncIterator[str]:
    while (event := await queue.get()) is not None:
        yield frame(event)


@router.post("/{conversation_id}/turns")
async def create_turn(
    conversation_id: UUID,
    turn: TurnRequest,
    request: Request,
    store: Store = Depends(get_store),
) -> StreamingResponse:
    conversation = await _load(store, conversation_id)
    if conversation.message_count == 0:
        await store.rename_conversation(conversation_id, title_from(turn.message))
    await store.add_message(conversation_id, "user", turn.message)

    # Unbounded on purpose: if the client disconnects nobody drains this, and the run
    # must not block on a queue no one is reading. Progress events are few and tiny.
    queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
    task = asyncio.create_task(_run_turn(request.app.state.agent, store, conversation_id, turn, queue))
    # Without a reference the loop may garbage-collect the task mid-run.
    request.app.state.turns.add(task)
    task.add_done_callback(request.app.state.turns.discard)

    return StreamingResponse(_drain(queue), media_type="text/event-stream", headers=SSE_HEADERS)
