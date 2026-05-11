"""Ownership boundary for agent sessions.

A `thread_id` is bound to the first `user_id` that uses it. Any subsequent
attempt by a different `user_id` to use the same `thread_id` is rejected with
`OwnershipError`.

Concrete `AgentService` implementations must call
`ownership_store.bind_or_verify(session_context.thread_id, session_context.user_id)`
before invoking the graph, and convert any `OwnershipError` into an `ErrorEvent`
to preserve the no-raise contract.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from library.exceptions import OwnershipError


class OwnershipStore(ABC):
    """Abstract ownership registry.

    Binds a `thread_id` to a `user_id` on first use and enforces that
    subsequent uses by a different `user_id` are rejected.
    """

    @abstractmethod
    def bind_or_verify(self, thread_id: str, user_id: str) -> None:
        """Bind thread_id to user_id on first use, or verify ownership on subsequent calls.

        Args:
            thread_id: The conversation thread identifier to bind.
            user_id: The user claiming ownership of this thread.

        Raises:
            OwnershipError: If thread_id is already bound to a different user_id.
        """


class InMemoryOwnershipStore(OwnershipStore):
    """Thread-safe in-memory ownership store.

    Suitable for single-process deployments and testing.  For multi-process
    or distributed deployments, replace with a Redis- or DB-backed
    implementation that satisfies the same `OwnershipStore` interface.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, str] = {}

    def bind_or_verify(self, thread_id: str, user_id: str) -> None:
        """Bind or verify ownership; raise `OwnershipError` on mismatch."""
        with self._lock:
            owner = self._store.get(thread_id)
            if owner is None:
                # First bind - register ownership.
                self._store[thread_id] = user_id
                return
            if owner != user_id:
                raise OwnershipError(
                    f"Thread '{thread_id}' is owned by a different user. "
                    f"Access denied for user '{user_id}'."
                )
            # Same user - idempotent, nothing to do.


__all__ = ["InMemoryOwnershipStore", "OwnershipStore"]
