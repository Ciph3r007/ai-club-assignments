# src/library/db/sql_guard.py
"""Read-only SQL safety guard.

Validates SQL statements against a pipeline of `SqlValidationRule` objects.
Rules are data — add, remove, or reorder entries in `_RULES` without
touching control flow. Only plain SELECT statements without destructive
keywords are accepted.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from library.exceptions import SqlGuardError

_DESTRUCTIVE_RE = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|TRUNCATE|GRANT|REVOKE"
    r"|EXEC|EXECUTE|MERGE|REPLACE|CALL)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SqlValidationRule:
    """A single, immutable SQL validation predicate.

    `check` receives the normalised SQL string and returns `True` when the
    statement passes the rule.  `error` is raised as `SqlGuardError` on
    failure.
    """

    name: str
    check: Callable[[str], bool]
    error: str


_RULES: tuple[SqlValidationRule, ...] = (
    SqlValidationRule(
        name="non-empty",
        check=lambda s: bool(s),
        error="SQL must not be empty.",
    ),
    SqlValidationRule(
        name="select-only",
        check=lambda s: bool(re.match(r"^SELECT\b", s, re.IGNORECASE)),
        error=(
            "Only SELECT statements are permitted. "
            "Received statement starting with: {prefix!r}"
        ),
    ),
    SqlValidationRule(
        name="no-semicolon",
        check=lambda s: ";" not in s,
        error="Multi-statement SQL is not permitted. Remove the semicolon.",
    ),
    SqlValidationRule(
        name="no-mutation",
        check=lambda s: not bool(_DESTRUCTIVE_RE.search(s)),
        error="Destructive keyword detected. Only read-only SELECT queries are allowed.",
    ),
)


def validate_sql(sql: str) -> str:
    """Validate *sql* against `_RULES` and return the normalised statement.

    Raises `SqlGuardError` on the first failing rule.  The error message for
    the `select-only` rule is interpolated with the actual statement prefix.
    """
    normalized = sql.strip().rstrip(";").strip()
    for rule in _RULES:
        if not rule.check(normalized):
            msg = rule.error
            if "{prefix" in msg:
                msg = msg.format(prefix=normalized[:20])
            raise SqlGuardError(msg)
    return normalized


__all__ = ["SqlValidationRule", "_RULES", "validate_sql"]
