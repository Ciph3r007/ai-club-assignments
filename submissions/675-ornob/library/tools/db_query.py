# src/library/tools/db_query.py
"""DB query tool handler."""

from __future__ import annotations

from typing import Any

from library.api.events import DbResultEvent, ErrorEvent
from library.db.execution import execute_sql
from library.db.query_executor import QueryExecutor
from library.exceptions import QueryGraphError, SqlGuardError
from library.tools.error_mapper import ErrorMapper

_ERRORS = ErrorMapper(
    mapping=(
        (SqlGuardError, "SqlGuardError"),
        (QueryGraphError, "QueryGraphError"),
    )
)


class RunSqlHandler:
    """Executes a validated SQL SELECT query and returns a ``DbResultEvent``."""

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> DbResultEvent | ErrorEvent:
        query: str = kwargs.get("query")
        if not query:
            return ErrorEvent(error_type="ConfigurationError", message="Missing required 'query'.")
        try:
            result = await execute_sql(query, executor)
        except Exception as exc:  # noqa: BLE001
            return _ERRORS.to_event(exc)
        return DbResultEvent(
            sql=result.sql,
            rows=result.rows,
            row_count=0,  # overwritten by model_validator
        )


async def handle_run_sql(query: str, executor: QueryExecutor) -> DbResultEvent | ErrorEvent:
    return await RunSqlHandler().handle(executor, query=query)


__all__ = ["RunSqlHandler", "handle_run_sql"]
