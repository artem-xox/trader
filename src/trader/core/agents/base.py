from __future__ import annotations

from collections.abc import Callable

from langgraph.utils.runnable import RunnableCallable

from trader.common.config import Settings, get_settings


def silent_router(func: Callable) -> RunnableCallable:
    """Wrap a conditional-edge router so LangGraph runs it without emitting a trace span.

    Routing functions otherwise surface as `_route_after_*` runs that clutter the trace with
    no signal — the branch they pick is already visible from the next node that runs.
    `trace=False` keeps the routing behaviour but suppresses the span.
    """
    return RunnableCallable(func, name=getattr(func, "__name__", "route"), trace=False)


class BaseAgent:
    """Common base: holds settings. The agent interface is `models.protocols.Agent`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
