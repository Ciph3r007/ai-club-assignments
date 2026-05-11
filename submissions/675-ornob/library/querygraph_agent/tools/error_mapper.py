"""Exception-to-ErrorEvent lookup table.

Replaces multi-except chains in tool handlers.  Each handler owns an
``ErrorMapper`` instance that maps exception types to ``ErrorEvent`` error_type
strings.  The first matching type wins; if none match, ``"UnknownError"`` is
returned.

IMPORTANT — tuple ordering: subclasses MUST appear before their parent types.
If a parent appears first, all subclass entries after it become unreachable
(``isinstance`` matches the parent first).  The constructor validates this and
raises ``ConfigurationError`` for invalid orderings.

Usage::

    _ERRORS = ErrorMapper(mapping=(
        (SqlGuardError, "SqlGuardError"),   # subclass first
        (QueryGraphError, "QueryGraphError"),  # parent after
    ))

    try:
        result = await do_something()
    except Exception as exc:
        return _ERRORS.to_event(exc)
"""

from __future__ import annotations

from dataclasses import dataclass

from querygraph_agent.api.events import ErrorEvent
from querygraph_agent.exceptions import ConfigurationError


@dataclass(frozen=True)
class ErrorMapper:
    """Maps exception types to ``ErrorEvent`` without multi-except chains.

    Raises ``ConfigurationError`` at construction if any parent type appears
    before one of its subclasses in *mapping* (which would make that subclass
    entry unreachable).
    """

    mapping: tuple[tuple[type[Exception], str], ...]

    def __post_init__(self) -> None:
        for i, (earlier_type, _) in enumerate(self.mapping):
            for later_type, _ in self.mapping[i + 1 :]:
                if issubclass(later_type, earlier_type):
                    raise ConfigurationError(
                        f"ErrorMapper: {later_type.__name__} is a subclass of "
                        f"{earlier_type.__name__} but appears after it in the mapping. "
                        f"Subclasses must be listed before their parent types."
                    )

    def to_event(self, exc: Exception) -> ErrorEvent:
        for exc_type, error_type in self.mapping:
            if isinstance(exc, exc_type):
                return ErrorEvent(error_type=error_type, message=str(exc))
        return ErrorEvent(
            error_type="UnknownError",
            message=f"Unexpected error: {exc}",
        )


__all__ = ["ErrorMapper"]
