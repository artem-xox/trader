"""Responder prompt for normal mode (no active skill).

Skill-specific prompts live with their skill (see `trader.core.skills`) and are appended
to this base; in normal mode only this base prompt is used.
"""

BASE_RESPONDER_PROMPT = """Write the final answer to the user.

Read the conversation above (including any tool results) and put a clear, concise reply
in the `summary` field.
"""
