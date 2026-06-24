"""Static user-facing strings for the Telegram bot, kept out of the handler logic."""

from __future__ import annotations

HELP = (
    "👋 I'm AI Trader.\n\n"
    "Just send me a topic and I'll research interesting Polymarket bets.\n"
    "• /find <topic> — find interesting bets on a topic.\n"
    "• /analyze <market url> — deep dive on one market with a risk model.\n"
    "• /clear — start a fresh chat with empty history.\n"
    "Example: /find bitcoin price 2026"
)

NOT_ALLOWED = "Sorry, you are not on the allowlist."

THINKING = "💭 Thinking…"

RESEARCH_FAILED = "⚠️ Something went wrong while researching. Try again."

HISTORY_CLEARED = "🧹 History cleared. Starting fresh."

USAGE_FIND = "Usage: /find <topic>"

USAGE_ANALYZE = "Usage: /analyze <market url>"
