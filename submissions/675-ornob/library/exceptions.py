"""Package-level domain exceptions for library.

All exceptions inherit from `QueryGraphError` so callers can catch the
entire family with a single `except QueryGraphError` clause while still
being able to handle specific sub-cases precisely.
"""

from __future__ import annotations


class QueryGraphError(Exception):
    """Base exception for all querygraph-agent errors."""


class OwnershipError(QueryGraphError):
    """Raised when a resource is accessed by an unauthorised user.

    Typically triggered when the `user_id` in the session context does not
    own the resource being requested.
    """


class SqlGuardError(QueryGraphError):
    """Raised when a generated SQL statement fails safety validation.

    The guard rejects statements that contain mutation keywords (INSERT,
    UPDATE, DELETE, DROP, ...) or other patterns not permitted by policy.
    """


class ModelToolCallError(QueryGraphError):
    """Raised when an LLM tool invocation fails at the model/transport layer.

    This wraps lower-level errors (timeouts, malformed responses, etc.) so
    the rest of the system can handle them uniformly as typed domain errors.
    """


class ConfigurationError(QueryGraphError):
    """Raised when required configuration is missing or invalid.

    Examples: missing environment variables, unsupported model names,
    or database connection strings that cannot be parsed.
    """
