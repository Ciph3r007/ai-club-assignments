# src/library/tools/think.py
"""Think tool handler."""

from __future__ import annotations

from typing import Any

from library.api.events import ThinkingEvent
from library.db.query_executor import QueryExecutor


class ThinkHandler:
    """Wraps a reasoning string in a `ThinkingEvent`."""

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> ThinkingEvent:
        """Wrap the reasoning string in a ThinkingEvent.

        Args:
            executor: Not used by this tool; accepted to satisfy the handler protocol.
            **kwargs: Must contain a `thought` key with the reasoning string.

        Returns:
            ThinkingEvent containing the thought string.
        """
        return ThinkingEvent(content=kwargs["thought"])


# Backward-compatible module-level function (used by notebooks directly).
def handle_think(thought: str) -> ThinkingEvent:
    """Return a `ThinkingEvent` for *thought*."""
    return ThinkingEvent(content=thought)


__all__ = ["ThinkHandler", "handle_think"]
