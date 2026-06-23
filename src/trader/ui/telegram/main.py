"""Telegram bot (aiogram).

Runs locally via long-polling — no public webhook needed for development. Each message
is forwarded to the agent HTTP app; the agent's answer is sent back to the chat.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import telegramify_markdown
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from dotenv import load_dotenv

from trader.common.config import get_settings

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
dp = Dispatcher()


def _allowed(chat_id: int) -> bool:
    allowed = settings.telegram_allowed_chat_ids
    return not allowed or chat_id in allowed


async def _ask_agent(message: str, thread_id: str) -> str:
    url = f"{settings.agent_app_url}/agent/invoke"
    headers = {"X-API-Key": settings.agent_api_key} if settings.agent_api_key else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.post(url, json={"message": message, "thread_id": thread_id}, headers=headers)
        resp.raise_for_status()
        return resp.json()["response"]


async def _research_and_reply(message: Message, prompt: str) -> None:
    """Send the prompt to the agent and reply with its formatted answer."""
    if not _allowed(message.chat.id):
        await message.answer("Sorry, you are not on the allowlist.")
        return

    await message.answer("🔎 Researching…")
    try:
        answer = await _ask_agent(prompt, thread_id=str(message.chat.id))
    except Exception:  # noqa: BLE001 - surface a friendly error, log details
        logger.exception("agent call failed")
        await message.answer("⚠️ Something went wrong while researching. Try again.")
        return
    await message.answer(
        telegramify_markdown.markdownify(answer),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@dp.message(Command("start", "help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "👋 I'm AI Trader.\n\n"
        "Just send me a topic and I'll research interesting Polymarket bets.\n"
        "• /find <topic> — find interesting bets on a topic.\n"
        "• /analyze <market url> — deep dive on one market with a risk model.\n"
        "Example: /find bitcoin price 2026"
    )


@dp.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip():
        await message.answer("Usage: /find <topic>")
        return
    # Forward the full text (incl. "/find") so the agent's skills node activates `find`.
    await _research_and_reply(message, message.text)


@dp.message(Command("analyze"))
async def cmd_analyze(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip():
        await message.answer("Usage: /analyze <market url>")
        return
    # Forward the full text (incl. "/analyze") so the agent's skills node activates `analyze`.
    await _research_and_reply(message, message.text)


@dp.message(F.text & ~F.text.startswith("/"))
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
