"""Exception-to-ErrorEvent lookup table.

Replaces multi-except chains in tool handlers. Each handler owns an
`ErrorMapper` instance that maps exception types to `ErrorEvent` error_type
strings. The first matching type wins; if none match, "UnknownError" is used.

Subclasses MUST appear before their parent types in the mapping. If a parent
appears first, all subclass entries after it become unreachable because
isinstance matches the parent first. The constructor validates ordering and
raises ConfigurationError for invalid mappings.

Example usage:

    _ERRORS = ErrorMapper(mapping=(
        (SqlGuardError, "SqlGuardError"),    # subclass first
        (QueryGraphError, "QueryGraphError"),  # parent after
    ))

    try:
        result = await do_something()
    except Exception as exc:
        return _ERRORS.to_event(exc)
"""

from __future__ import annotations

from dataclasses import dataclass

from library.api.events import ErrorEvent
from library.exceptions import ConfigurationError


@dataclass(frozen=True)
class ErrorMapper:
    """Maps exception types to `ErrorEvent` without multi-except chains.

    Raises `ConfigurationError` at construction if any parent type appears
    before one of its subclasses in *mapping* (which would make that subclass
    entry unreachable).
    """

    mapping: tuple[tuple[type[Exception], str], ...]

    def __post_init__(self) -> None:
        """Validate that no parent type appears before a subclass in the mapping."""
        for i, (earlier_type, _) in enumerate(self.mapping):
            for later_type, _ in self.mapping[i + 1 :]:
                if issubclass(later_type, earlier_type):
                    raise ConfigurationError(
                        f"ErrorMapper: {later_type.__name__} is a subclass of "
                        f"{earlier_type.__name__} but appears after it in the mapping. "
                        f"Subclasses must be listed before their parent types."
                    )

    def to_event(self, exc: Exception) -> ErrorEvent:
        """Map an exception to an ErrorEvent using the registered mapping.

        The first matching type wins. If no type matches, returns an ErrorEvent
        with error_type="UnknownError".

        Args:
            exc: The exception to convert.

        Returns:
            ErrorEvent with the matched error_type and the exception message.
        """
        for exc_type, error_type in self.mapping:
            if isinstance(exc, exc_type):
                return ErrorEvent(error_type=error_type, message=str(exc))
        return ErrorEvent(
            error_type="UnknownError",
            message=f"Unexpected error: {exc}",
        )


__all__ = ["ErrorMapper"]
