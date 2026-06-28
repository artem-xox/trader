"""Telegram bot (aiogram).

Runs locally via long-polling — no public webhook needed for development. Each message
is forwarded to the agent HTTP app; the agent's answer is sent back to the chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import httpx
import telegramify_markdown
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from dotenv import load_dotenv

from trader.common.config import get_settings
from trader.ui.telegram.content import messages

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
dp = Dispatcher()

# Per-chat conversation epoch. Bumping it changes the agent thread id, so the next
# message starts from an empty history (see `/clear`).
_chat_epoch: dict[int, int] = {}

# Chats with debug mode on; while set, answers carry a LangSmith trace link (see `/debug`).
_debug_chats: set[int] = set()


def _allowed(chat_id: int) -> bool:
    allowed = settings.telegram_allowed_chat_ids
    return not allowed or chat_id in allowed


def _thread_id(chat_id: int) -> str:
    return f"{chat_id}:{_chat_epoch.get(chat_id, 0)}"


def _to_markdown_v2(markdown: str) -> str:
    """Convert agent markdown to Telegram MarkdownV2.

    `telegramify_markdown` reads `$…$` as LaTeX and renders the span monospace; our answers
    carry plain dollar prices, so escape `$` to keep them literal text.
    """
    return telegramify_markdown.markdownify(markdown.replace("$", r"\$"))


Handler = TypeVar("Handler", bound=Callable[..., Awaitable[Any]])


def allowlisted(handler: Handler) -> Handler:
    """Reject messages from chats not on the allowlist before running `handler`."""

    @wraps(handler)
    async def wrapper(message: Message, *args: Any, **kwargs: Any) -> Any:
        if not _allowed(message.chat.id):
            await message.answer(messages.NOT_ALLOWED)
            return None
        return await handler(message, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


# Telegram throttles message edits; ~1/s stays clear of 429s while still feeling live.
_MIN_EDIT_INTERVAL = 1.0


async def _stream_agent(prompt: str, thread_id: str, *, debug: bool) -> AsyncIterator[dict[str, Any]]:
    """Yield the agent's SSE progress events as dicts (status… then a terminal final/error)."""
    url = f"{settings.agent_app_url}/agent/stream"
    headers = {"X-API-Key": settings.agent_api_key} if settings.agent_api_key else {}
    payload = {"message": prompt, "thread_id": thread_id, "debug": debug}
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    yield json.loads(line[5:].strip())


async def _research_and_reply(message: Message, prompt: str) -> None:
    """Stream the agent run, editing one status message live, then post the final answer."""
    debug = message.chat.id in _debug_chats
    status = await message.answer(messages.THINKING)
    last_text, last_edit, final = messages.THINKING, 0.0, None
    try:
        async for event in _stream_agent(prompt, _thread_id(message.chat.id), debug=debug):
            kind = event.get("kind")
            if kind == "final":
                final = event
            elif kind == "error":
                raise RuntimeError("agent stream returned an error")
            elif kind == "status":
                text = messages.status_line(event.get("label", ""), event.get("detail"))
                now = time.monotonic()
                if text != last_text and now - last_edit >= _MIN_EDIT_INTERVAL:
                    try:
                        await status.edit_text(text)
                    except Exception:  # noqa: BLE001 - a failed status edit must not abort the run
                        pass
                    last_text, last_edit = text, now
    except Exception:  # noqa: BLE001 - surface a friendly error, log details
        logger.exception("agent stream failed")
        await status.delete()
        await message.answer(messages.RESEARCH_FAILED)
        return
    await status.delete()
    if not final or not final.get("response"):
        await message.answer(messages.RESEARCH_FAILED)
        return
    await message.answer(
        _to_markdown_v2(final["response"]),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    if debug and final.get("trace_url"):
        await message.answer(messages.trace_link(final["trace_url"]), disable_web_page_preview=True)


@dp.message(Command("start", "help"))
@allowlisted
async def cmd_help(message: Message) -> None:
    await message.answer(messages.HELP)


@dp.message(Command("clear"))
@allowlisted
async def cmd_clear(message: Message) -> None:
    _chat_epoch[message.chat.id] = _chat_epoch.get(message.chat.id, 0) + 1
    await message.answer(messages.HISTORY_CLEARED)


@dp.message(Command("debug"))
@allowlisted
async def cmd_debug(message: Message) -> None:
    chat_id = message.chat.id
    if chat_id in _debug_chats:
        _debug_chats.discard(chat_id)
        await message.answer(messages.DEBUG_OFF)
        return
    _debug_chats.add(chat_id)
    await message.answer(messages.DEBUG_ON)


@dp.message(Command("find"))
@allowlisted
async def cmd_find(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip():
        await message.answer(messages.USAGE_FIND)
        return
    # Forward the full text (incl. "/find") so the agent's skills node activates `find`.
    await _research_and_reply(message, message.text)


@dp.message(Command("analyze"))
@allowlisted
async def cmd_analyze(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip():
        await message.answer(messages.USAGE_ANALYZE)
        return
    # Forward the full text (incl. "/analyze") so the agent's skills node activates `analyze`.
    await _research_and_reply(message, message.text)


@dp.message(F.text & ~F.text.startswith("/"))
@allowlisted
async def any_message(message: Message) -> None:
    await _research_and_reply(message, message.text)


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    bot = Bot(token=settings.telegram_bot_token)
    logger.info("Bot starting (long-polling)…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
