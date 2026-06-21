"""Telegram bot (aiogram).

Runs locally via long-polling — no public webhook needed for development. Each message
is forwarded to the agent HTTP app; the agent's answer is sent back to the chat.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import telegramify_markdown
from aiogram import Bot, Dispatcher
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
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.post(url, json={"message": message, "thread_id": thread_id})
        resp.raise_for_status()
        return resp.json()["response"]


@dp.message(Command("start", "help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "👋 I'm AI Trader.\n\n"
        "Use /find <topic> to research interesting Polymarket bets.\n"
        "Example: /find bitcoin price 2026"
    )


@dp.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject) -> None:
    if not _allowed(message.chat.id):
        await message.answer("Sorry, you are not on the allowlist.")
        return

    topic = (command.args or "").strip()
    if not topic:
        await message.answer("Usage: /find <topic>")
        return

    await message.answer("🔎 Researching…")
    try:
        answer = await _ask_agent(topic, thread_id=str(message.chat.id))
    except Exception:  # noqa: BLE001 - surface a friendly error, log details
        logger.exception("agent call failed")
        await message.answer("⚠️ Something went wrong while researching. Try again.")
        return
    await message.answer(
        telegramify_markdown.markdownify(answer),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    bot = Bot(token=settings.telegram_bot_token)
    logger.info("Bot starting (long-polling)…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
