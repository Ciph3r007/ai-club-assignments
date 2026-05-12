"""Agent service contract — `SessionContext` and the `AgentService` abstract base class.

`run_turn` returns all events at once after the turn completes.
`stream_turn` yields events incrementally as the agent produces them.

Both methods always end with `DoneEvent`. Errors are returned as `ErrorEvent`
objects inside the list/stream — never raised — so callers always get a
consistent result regardless of what went wrong.

Multi-turn memory is keyed on `session_context.thread_id`. Reusing the same
`thread_id` across calls enables follow-up questions. A new `thread_id`
starts a fresh conversation with no prior context.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from library.api.events import AgentEvent

if TYPE_CHECKING:
    from library.api.events import ErrorEvent
    from library.session.ownership import OwnershipStore


class SessionContext(BaseModel):
    """Required context the caller must supply for every agent turn.

    Attributes:
        thread_id: Stable key for LangGraph conversation memory. Reuse across
            turns to enable multi-turn continuity. A new value starts a fresh
            session with no prior context.
        user_id: Identifies the calling user. Used for ownership checks —
            only the first user to claim a thread_id may continue it.
    """

    thread_id: str = Field(
        ...,
        min_length=1,
        description="Stable conversation key for LangGraph memory.",
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="Caller identity for ownership and authorisation checks.",
    )

    model_config = {"frozen": True}


class AgentService(abc.ABC):
    """Abstract base class for the agent service.

    Concrete implementations must call `ownership_store.bind_or_verify(thread_id, user_id)`
    as the first action in both `run_turn` and `stream_turn`. Any `OwnershipError`
    must be caught and converted into an `ErrorEvent` to preserve the no-raise contract.
    """

    @abc.abstractmethod
    async def run_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> list[AgentEvent]:
        """Execute one conversational turn and return all events.

        Args:
            session_context: Caller-supplied context with thread_id and user_id.
            user_message: The natural-language message from the user.

        Returns:
            list[AgentEvent]: Ordered events for the turn. Errors appear as
                `ErrorEvent` entries — never raised as exceptions.
        """

    @abc.abstractmethod
    def stream_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute one conversational turn and yield events as they are produced.

        Args:
            session_context: Caller-supplied context with thread_id and user_id.
            user_message: The natural-language message from the user.

        Yields:
            AgentEvent: Events in production order. Always ends with `DoneEvent`.
                Errors appear as `ErrorEvent` objects — never raised as exceptions.
        """

    def _check_ownership(
        self,
        session_context: SessionContext,
        ownership_store: OwnershipStore,
    ) -> ErrorEvent | None:
        """Verify thread ownership. Call this at the start of run_turn/stream_turn.

        Args:
            session_context: Caller-supplied context with thread_id and user_id.
            ownership_store: The ownership registry to check against.

        Returns:
            ErrorEvent | None: None if ownership is confirmed. An ErrorEvent with
                error_type="OwnershipError" if a different user owns this thread.
        """
        from library.api.events import ErrorEvent as _ErrorEvent
        from library.exceptions import OwnershipError

        try:
            ownership_store.bind_or_verify(session_context.thread_id, session_context.user_id)
            return None
        except OwnershipError as exc:
            return _ErrorEvent(error_type="OwnershipError", message=str(exc))


__all__ = [
    "AgentService",
    "SessionContext",
]
