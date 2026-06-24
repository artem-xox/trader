from __future__ import annotations

from pydantic import BaseModel, Field
from trader.core.models.schemas import GuardVerdict


class GuardJudgment(BaseModel):
    reason: str = Field(description="One-line justification with small reasoning.")
    verdict: GuardVerdict = Field(description="Whether the proposed tool calls may run.")
