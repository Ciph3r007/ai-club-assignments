"""Stable library-facing agent service contract.

This module defines:

- ``SessionContext`` - required caller-supplied context for every turn.
- ``AgentService`` - abstract base class that concrete implementations must
  subclass.  At this stage it contains no runnable logic; implementations are
  added in Tasks 5-6 once LangGraph and tools are in place.

Public API
----------
Two methods are exposed:

``run_turn(session_context, user_message) -> list[AgentEvent]``
    Execute a single conversational turn and return *all* events at once.
    Errors are returned as ``ErrorEvent`` entries in the list - never raised
    directly - so callers get the same deterministic error representation
    regardless of which mode they use.

``stream_turn(session_context, user_message) -> AsyncGenerator[AgentEvent, None]``
    Same semantics as ``run_turn`` but yields events incrementally as the
    agent produces them.  The stream is always terminated by a ``DoneEvent``
    (or an ``ErrorEvent`` followed by a ``DoneEvent`` on failure).

Session continuity
------------------
Multi-turn memory is keyed on ``session_context.thread_id``.  Reusing the
same ``thread_id`` across calls is what enables follow-up questions to refer
to previous answers.  A fresh ``thread_id`` starts a new conversation with no
prior context.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from querygraph_agent.api.events import AgentEvent

if TYPE_CHECKING:
    from querygraph_agent.api.events import ErrorEvent
    from querygraph_agent.session.ownership import OwnershipStore


class SessionContext(BaseModel):
    """Required context that the caller must supply for every agent turn.

    Fields
    ------
    thread_id
        Stable key used to persist and retrieve conversation memory in
        LangGraph's checkpointer.  Reuse the same value across turns to
        enable multi-turn continuity.  A new value starts a fresh session.
    user_id
        Identifies the calling user.  Used for ownership boundary checks and
        authorisation decisions within the agent.
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

    Concrete implementations are introduced in Tasks 5-6.  Tests in this task
    verify the contract shape (method signatures, return types) by subclassing
    this ABC with minimal stubs.

    Ownership precondition (REQ-OWN-001)
    -------------------------------------
    Concrete implementations MUST call::

        ownership_store.bind_or_verify(
            session_context.thread_id,
            session_context.user_id,
        )

    as the first action inside both ``run_turn`` and ``stream_turn``, before
    any graph invocation.  Any ``OwnershipError`` raised by the store must be
    caught and converted into an ``ErrorEvent`` so that the no-raise contract
    is preserved for callers.
    """

    @abc.abstractmethod
    async def run_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> list[AgentEvent]:
        """Execute one conversational turn and return all events.

        Parameters
        ----------
        session_context:
            Caller-supplied context.  Both ``thread_id`` and ``user_id`` are
            required and must be non-empty strings.
        user_message:
            The natural-language message from the user.

        Returns
        -------
        list[AgentEvent]
            Ordered sequence of events produced during the turn.  Model or
            tool errors are represented as ``ErrorEvent`` entries in the list;
            they are not raised as exceptions.
        """

    @abc.abstractmethod
    def stream_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute one conversational turn and yield events as they are produced.

        Parameters
        ----------
        session_context:
            Caller-supplied context.  Both ``thread_id`` and ``user_id`` are
            required and must be non-empty strings.
        user_message:
            The natural-language message from the user.

        Yields
        ------
        AgentEvent
            Events in production order.  The stream always ends with a
            ``DoneEvent``, even when an error occurs.  Error semantics are
            identical to ``run_turn``: errors appear as ``ErrorEvent`` objects,
            never as raised exceptions.
        """

    def _check_ownership(
        self,
        session_context: SessionContext,
        ownership_store: OwnershipStore,
    ) -> ErrorEvent | None:
        """Call at the start of run_turn/stream_turn. Returns ErrorEvent if ownership rejected.

        Parameters
        ----------
        session_context:
            The caller-supplied context containing ``thread_id`` and ``user_id``.
        ownership_store:
            The ownership registry to consult.  Must implement
            ``OwnershipStore.bind_or_verify``.

        Returns
        -------
        ErrorEvent | None
            ``None`` when ownership is confirmed (first use or same user).
            An ``ErrorEvent`` with ``error_type="OwnershipError"`` when a
            different user attempts to access a thread they do not own.
        """
        from querygraph_agent.api.events import ErrorEvent as _ErrorEvent
        from querygraph_agent.exceptions import OwnershipError

        try:
            ownership_store.bind_or_verify(session_context.thread_id, session_context.user_id)
            return None
        except OwnershipError as exc:
            return _ErrorEvent(error_type="OwnershipError", message=str(exc))


__all__ = [
    "AgentService",
    "SessionContext",
]
