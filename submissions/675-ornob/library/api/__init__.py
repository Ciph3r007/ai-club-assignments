"""Public API package for library.

Stable symbols re-exported here for convenient imports:

    from library.api import AgentService, SessionContext
    from library.api import ThinkingEvent, AssistantTextEvent, ...
"""

from library.api.events import (
    AgentEvent,
    AssistantTextEvent,
    DbResultEvent,
    DoneEvent,
    ErrorEvent,
    ThinkingEvent,
)
from library.api.service import AgentService, SessionContext

__all__ = [
    "AgentEvent",
    "AgentService",
    "AssistantTextEvent",
    "DbResultEvent",
    "DoneEvent",
    "ErrorEvent",
    "SessionContext",
    "ThinkingEvent",
]
