"""Trading logic: deterministic market-quality and execution-cost models.

Pure functions only — no network, no LLM. Home for the Phase 2 tradability score and,
later, the Phase 1 cost/EV/sizing models and Phase 3 portfolio caps.
"""

from trader.core.trading.scoring import (
    MAX_SPREAD_BPS,
    MIN_DEPTH_USD,
    WEIGHTS,
    tradability,
)

__all__ = ["MAX_SPREAD_BPS", "MIN_DEPTH_USD", "WEIGHTS", "tradability"]
