# src/library/tools/db_schema.py
"""DB schema inspection tool handler."""

from __future__ import annotations

from typing import Any

from library.api.events import ErrorEvent, ThinkingEvent
from library.db.query_executor import QueryExecutor
from library.exceptions import QueryGraphError
from library.tools.error_mapper import ErrorMapper

_ERRORS = ErrorMapper(
    mapping=(
        (QueryGraphError, "QueryGraphError"),
    )
)


class DbSchemaHandler:
    """Inspects database schema metadata and returns it as a `ThinkingEvent`."""

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> ThinkingEvent | ErrorEvent:
        """Fetch schema metadata and return it as a ThinkingEvent.

        Args:
            executor: The database executor used to query information_schema.
            **kwargs: May contain `table_name` (str | None) to filter results.

        Returns:
            ThinkingEvent with formatted schema text, or ErrorEvent on failure.
        """
        table_name: str | None = kwargs.get("table_name")
        try:
            schema = await executor.inspect_schema(table_name=table_name)
        except Exception as exc:  # noqa: BLE001
            return _ERRORS.to_event(exc)
        return ThinkingEvent(content=str(schema))


# Backward-compatible module-level function (used by notebooks directly).
async def handle_db_schema(
    executor: QueryExecutor,
    table_name: str | None = None,
) -> ThinkingEvent | ErrorEvent:
    """Fetch schema metadata for one table or all tables."""
    return await DbSchemaHandler().handle(executor, table_name=table_name)


__all__ = ["DbSchemaHandler", "handle_db_schema"]
