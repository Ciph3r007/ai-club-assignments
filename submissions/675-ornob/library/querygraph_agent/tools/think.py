# src/querygraph_agent/tools/think.py
"""Think tool handler."""

from __future__ import annotations

from typing import Any

from querygraph_agent.api.events import ThinkingEvent
from querygraph_agent.db.query_executor import QueryExecutor


class ThinkHandler:
    """Wraps a reasoning string in a ``ThinkingEvent``."""

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> ThinkingEvent:
        return ThinkingEvent(content=kwargs["thought"])


# Backward-compatible module-level function (used by notebooks directly).
def handle_think(thought: str) -> ThinkingEvent:
    """Return a ``ThinkingEvent`` for *thought*."""
    return ThinkingEvent(content=thought)


__all__ = ["ThinkHandler", "handle_think"]
