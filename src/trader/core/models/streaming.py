"""Progress events streamed while the agent runs.

The agent emits these as its graph advances, so a client can show live progress
("searching…", "thinking…") instead of one static placeholder. Events are *semantic*
(a `label` like "tool:web_search" plus an optional `detail`); the rendering — emoji,
wording, language — is the client's job. The final event carries the structured result.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from trader.core.models.domain import SkillResult


class ProgressEvent(BaseModel):
    kind: Literal["status", "final"] = "status"
    # Semantic key for a status step, e.g. "skill:find", "tool:web_search", "synthesize".
    label: str = ""
    # Short human hint for the step (a search query, a market slug); None when not useful.
    detail: str | None = None
    # The structured answer, set only on the terminal `final` event.
    result: SkillResult | None = None
