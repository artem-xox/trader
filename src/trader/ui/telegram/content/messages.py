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


def trace_link(url: str) -> str:
    return f"🔗 Trace: {url}"


# Live-progress wording, keyed by the agent's semantic status label (see ProgressEvent).
_STATUS = {
    "skill:find": "🔎 Finding bets",
    "skill:analyze": "📊 Analyzing the market",
    "tool:polymarket_search": "🔎 Searching markets",
    "tool:polymarket_market": "📄 Reading the market",
    "tool:polymarket_orderbook": "📈 Reading the order book",
    "tool:web_search": "🌐 Searching the web",
    "tool:web_fetch": "🌐 Reading a page",
    "tool:calculator": "🧮 Crunching numbers",
    "tool:current_datetime": "🕐 Checking the date",
    "tool:think": "🤔 Thinking it through",
    "synthesize": "✍️ Writing the answer",
    "revise": "🔁 Refining the answer",
}


def status_line(label: str, detail: str | None = None) -> str:
    base = _STATUS.get(label, "💭 Working")
    return f"{base}: {detail}…" if detail else f"{base}…"
