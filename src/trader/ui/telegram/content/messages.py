"""Static user-facing strings for the Telegram bot, kept out of the handler logic."""

from __future__ import annotations

HELP = (
    "👋 I'm AI Trader.\n\n"
    "Just send me a topic and I'll research interesting Polymarket bets.\n"
    "• /find <topic> — find interesting bets on a topic.\n"
    "• /analyze <market url> — deep dive on one market with a risk model.\n"
    "• /clear — start a fresh chat with empty history.\n"
    "• /debug — toggle debug mode (attach a LangSmith trace to each answer).\n"
    "Example: /find bitcoin price 2026"
)

NOT_ALLOWED = "Sorry, you are not on the allowlist."

THINKING = "💭 Thinking…"

RESEARCH_FAILED = "⚠️ Something went wrong while researching. Try again."

HISTORY_CLEARED = "🧹 History cleared. Starting fresh."

USAGE_FIND = "Usage: /find <topic>"

USAGE_ANALYZE = "Usage: /analyze <market url>"

DEBUG_ON = "🐞 Debug mode ON. I'll attach a LangSmith trace link to each answer."

DEBUG_OFF = "✅ Debug mode OFF."

# Heads-up shown when debug is enabled but the bot has no LangSmith config of its own.
DEBUG_NO_TRACING = (
    "\n\nNote: LANGSMITH_TRACING isn't enabled here, so traces only appear if the "
    "agent service has tracing on."
)


def trace_link(url: str) -> str:
    return f"🔗 Trace: {url}"
