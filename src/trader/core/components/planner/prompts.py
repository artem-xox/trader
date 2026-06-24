"""Planner prompt for normal mode (no active skill).

Skill-specific prompts live with their skill (see `trader.core.skills`) and are appended
to this base; in normal mode only this base prompt is used.
"""

BASE_PLANNER_PROMPT = """You are a helpful, knowledgeable assistant.

Answer the user's request directly and accurately. Use the available tools when they
genuinely help (e.g. to look up current information); otherwise just answer from what you
know. Be concise.
"""
