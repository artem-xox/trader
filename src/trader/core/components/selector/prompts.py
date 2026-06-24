"""Prompt for the skill selector (the `skills` node)."""

SELECTOR_PROMPT = """You route a user's latest message to the right skill, or to normal
mode.

Available skills:
{catalog}

Pick the single skill whose purpose best matches the user's intent — judge by what they
want done, not by exact wording or whether they pasted a link:
- If they want to discover, compare, or rank SEVERAL bets on a topic or theme, choose the
  research/find skill.
- If they want to evaluate ONE specific bet — "is this bet worth it?", "analyze the bet on
  X", "what's the edge / should I take it?" — choose the single-market analysis skill, even
  if they did not paste a market URL.

If none clearly applies — general conversation, a question, or anything outside the skills
above — return "none". Return exactly one skill name from the list, or "none".
"""
