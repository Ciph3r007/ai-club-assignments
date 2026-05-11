"""Reusable SQL execution helpers built on top of ``QueryExecutor``.

This module provides lightweight, serializable result shaping for callers that
need a stable structure independent of SQLAlchemy internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from querygraph_agent.db.query_executor import QueryExecutor, QueryResult


@dataclass(frozen=True)
class SqlExecutionResult:
    """Serializable SQL execution result."""

    sql: str
    row_count: int
    rows: list[dict[str, Any]]


async def execute_sql(sql: str, executor: QueryExecutor) -> SqlExecutionResult:
    """Execute SQL via ``QueryExecutor`` and return a serializable result model."""
    result = await executor.execute(sql)
    return _to_execution_result(result)


def _to_execution_result(result: QueryResult) -> SqlExecutionResult:
    return SqlExecutionResult(
        sql=result.sql,
        row_count=result.row_count,
        rows=result.rows,
    )


__all__ = ["SqlExecutionResult", "execute_sql"]
