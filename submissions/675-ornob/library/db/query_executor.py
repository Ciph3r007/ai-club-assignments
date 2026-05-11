"""Bounded, read-only SQL query executor.

All queries are validated by `sql_guard.validate_sql` before execution.
Results are capped at `Settings.db_max_rows` rows.
Queries are bounded by `Settings.db_query_timeout_seconds`.
Connection errors are wrapped in `QueryGraphError` with a user-safe message.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from library.config.settings import Settings
from library.db.sql_guard import validate_sql
from library.exceptions import QueryGraphError


@dataclass
class QueryResult:
    """Structured result returned by `QueryExecutor.execute`."""

    sql: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0

    def __post_init__(self) -> None:
        self.row_count = len(self.rows)


@dataclass(frozen=True)
class ColumnInfo:
    """Metadata for a single database column."""

    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True)
class TableInfo:
    """Metadata for a single database table."""

    schema_name: str
    table_name: str
    columns: list[ColumnInfo]

    def __str__(self) -> str:
        lines = [f"{self.schema_name}.{self.table_name} ({len(self.columns)} columns):"]
        for col in self.columns:
            nullable = "NULL" if col.nullable else "NOT NULL"
            lines.append(f"  {col.name:<30} {col.data_type:<25} {nullable}")
        return "\n".join(lines)


@dataclass(frozen=True)
class SchemaInfo:
    """Aggregated schema metadata for one or more database tables."""

    tables: list[TableInfo]

    def __str__(self) -> str:
        if not self.tables:
            return "(no tables found)"
        return "\n\n".join(str(t) for t in self.tables)


_SYSTEM_SCHEMAS: tuple[str, ...] = (
    "information_schema",
    "pg_catalog",
    "pg_toast",
    "pg_toast_temp_0",
)

_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)

_LIMIT_STRATEGIES: dict[bool, Callable[[str, int], str]] = {
    True: lambda sql, _: sql,
    False: lambda sql, cap: f"{sql} LIMIT {cap}",
}

_SCHEMA_QUERY_FILTERED = """
    SELECT table_schema, table_name, column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = :table_name
      AND table_schema NOT IN :schemas
    ORDER BY table_schema, table_name, ordinal_position
"""

_SCHEMA_QUERY_ALL = """
    SELECT table_schema, table_name, column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema NOT IN :schemas
    ORDER BY table_schema, table_name, ordinal_position
"""

_SCHEMA_QUERIES: dict[bool, str] = {
    True: _SCHEMA_QUERY_FILTERED,
    False: _SCHEMA_QUERY_ALL,
}

_SCHEMA_PARAMS: dict[bool, Callable[[str | None], dict[str, Any]]] = {
    True: lambda t: {"table_name": t, "schemas": list(_SYSTEM_SCHEMAS)},
    False: lambda _: {"schemas": list(_SYSTEM_SCHEMAS)},
}


class QueryExecutor:
    """Execute validated, read-only SQL queries against the configured database.

    Uses synchronous SQLAlchemy (wrapped with `asyncio.to_thread`) so the
    caller can `await` the result without blocking the event loop.

    The engine is created once at construction time and reused across calls.
    Query timeout is enforced server-side via PostgreSQL `statement_timeout`,
    which ensures the DB cancels the query rather than leaving threads running.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def inspect_schema(self, table_name: str | None = None) -> SchemaInfo:
        """Inspect table/column metadata from `information_schema`.

        Args:
            table_name: When provided, restrict results to that table name across
                all non-system schemas. When None, returns all user tables.

        Returns:
            SchemaInfo: Aggregated column metadata grouped by table.

        Raises:
            QueryGraphError: If the DB connection or query fails.
        """
        try:
            return await asyncio.to_thread(self._run_schema_sync, table_name)
        except SQLAlchemyError as exc:
            raise QueryGraphError(f"Schema inspection failed: {exc}") from exc

    async def execute(self, sql: str) -> QueryResult:
        """Execute a validated SELECT statement and return a `QueryResult`.

        Raises:
            SqlGuardError: If the SQL fails the safety check.
            QueryGraphError: If the DB connection or query fails.
        """
        # Validate first (fast, synchronous, raises SqlGuardError if invalid).
        normalized_sql = validate_sql(sql)

        try:
            result = await asyncio.to_thread(self._run_sync, normalized_sql)
        except OperationalError as exc:
            raise QueryGraphError("Query timed out") from exc
        except SQLAlchemyError as exc:
            raise QueryGraphError(f"Database error while executing query: {exc}") from exc

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_sync(self, sql: str) -> QueryResult:
        """Execute sql synchronously, applying the row cap.

        Intended to be called via `asyncio.to_thread`.  Timeout is enforced
        server-side by setting `statement_timeout` on the connection.
        """
        limited_sql = self._apply_limit(sql)
        timeout_ms = int(self._settings.db_query_timeout_seconds * 1000)
        with self._engine.connect() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            cursor_result = conn.execute(text(limited_sql))
            rows = [
                dict(row._mapping) for row in cursor_result.fetchmany(self._settings.db_max_rows)
            ]
        return QueryResult(sql=sql, rows=rows)

    def _apply_limit(self, sql: str) -> str:
        """Append a LIMIT clause if the statement doesn't already have one."""
        return _LIMIT_STRATEGIES[bool(_LIMIT_RE.search(sql))](sql, self._settings.db_max_rows)

    def _run_schema_sync(self, table_name: str | None) -> SchemaInfo:
        """Query `information_schema.columns` synchronously.

        Intended to be called via `asyncio.to_thread`.
        """
        filtered = table_name is not None
        stmt = text(_SCHEMA_QUERIES[filtered]).bindparams(bindparam("schemas", expanding=True))
        params = _SCHEMA_PARAMS[filtered](table_name)

        with self._engine.connect() as conn:
            rows = conn.execute(stmt, params).fetchall()

        tables: dict[tuple[str, str], list[ColumnInfo]] = {}
        for row in rows:
            key = (row.table_schema, row.table_name)
            tables.setdefault(key, []).append(
                ColumnInfo(
                    name=row.column_name,
                    data_type=row.data_type,
                    nullable=row.is_nullable == "YES",
                )
            )

        return SchemaInfo(
            tables=[
                TableInfo(schema_name=schema, table_name=tbl, columns=cols)
                for (schema, tbl), cols in tables.items()
            ]
        )


__all__ = ["ColumnInfo", "QueryExecutor", "QueryResult", "SchemaInfo", "TableInfo"]
