# src/querygraph_agent/tools/db_schema.py
"""DB schema inspection tool handler."""

from __future__ import annotations

from typing import Any

from querygraph_agent.api.events import ErrorEvent, ThinkingEvent
from querygraph_agent.db.query_executor import QueryExecutor
from querygraph_agent.exceptions import QueryGraphError
from querygraph_agent.tools.error_mapper import ErrorMapper

_ERRORS = ErrorMapper(
    mapping=(
        (QueryGraphError, "QueryGraphError"),
    )
)


class DbSchemaHandler:
    """Inspects database schema metadata and returns it as a ``ThinkingEvent``."""

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> ThinkingEvent | ErrorEvent:
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
    return await DbSchemaHandler().handle(executor, table_name=table_name)


__all__ = ["DbSchemaHandler", "handle_db_schema"]
