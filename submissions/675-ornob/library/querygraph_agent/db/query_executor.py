"""Bounded, read-only SQL query executor.

REQ-DB-001 / NFR-DB-001 / NFR-DB-002:
- All queries are validated by ``sql_guard.validate_sql`` before execution.
- Results are capped at ``Settings.db_max_rows`` rows.
- Queries are bounded by ``Settings.db_query_timeout_seconds``.
- Connection errors are wrapped in ``QueryGraphError`` with a user-safe message.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from querygraph_agent.config.settings import Settings
from querygraph_agent.db.sql_guard import validate_sql
from querygraph_agent.exceptions import QueryGraphError


@dataclass
class QueryResult:
    """Structured result returned by ``QueryExecutor.execute``."""

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


class QueryExecutor:
    """Execute validated, read-only SQL queries against the configured database.

    Uses synchronous SQLAlchemy (wrapped with ``asyncio.to_thread``) so the
    caller can ``await`` the result without blocking the event loop.

    The engine is created once at construction time and reused across calls.
    Query timeout is enforced server-side via PostgreSQL ``statement_timeout``,
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
        """Inspect table/column metadata from ``information_schema``.

        Parameters
        ----------
        table_name:
            When provided, restrict results to that table name across all
            non-system schemas.  When ``None``, returns all user tables.

        Returns
        -------
        SchemaInfo
            Aggregated column metadata grouped by table.

        Raises
        ------
        QueryGraphError
            If the DB connection or query fails.
        """
        try:
            return await asyncio.to_thread(self._run_schema_sync, table_name)
        except SQLAlchemyError as exc:
            raise QueryGraphError(f"Schema inspection failed: {exc}") from exc

    async def execute(self, sql: str) -> QueryResult:
        """Execute a validated SELECT statement and return a ``QueryResult``.

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
        """Execute *sql* synchronously, applying the row cap.

        Intended to be called via ``asyncio.to_thread``.  Timeout is enforced
        server-side by setting ``statement_timeout`` on the connection.
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
        upper = sql.upper()
        if "LIMIT" not in upper:
            return f"{sql} LIMIT {self._settings.db_max_rows}"
        return sql

    def _run_schema_sync(self, table_name: str | None) -> SchemaInfo:
        """Query ``information_schema.columns`` synchronously.

        Intended to be called via ``asyncio.to_thread``.

        System schemas are excluded via a literal IN list - SQLAlchemy's
        ``text()`` does not expand Python tuples for parametrised IN clauses,
        so binding them as a parameter would cause a PostgreSQL syntax error.
        """
        _EXCLUDE = (
            "'information_schema', 'pg_catalog', 'pg_toast', 'pg_toast_temp_0'"
        )
        if table_name:
            stmt = text(
                f"""
                SELECT table_schema, table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = :table_name
                  AND table_schema NOT IN ({_EXCLUDE})
                ORDER BY table_schema, table_name, ordinal_position
                """
            )
            params: dict[str, Any] = {"table_name": table_name}
        else:
            stmt = text(
                f"""
                SELECT table_schema, table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema NOT IN ({_EXCLUDE})
                ORDER BY table_schema, table_name, ordinal_position
                """
            )
            params = {}

        with self._engine.connect() as conn:
            rows = conn.execute(stmt, params).fetchall()

        tables: dict[tuple[str, str], list[ColumnInfo]] = {}
        for row in rows:
            key = (row.table_schema, row.table_name)
            if key not in tables:
                tables[key] = []
            tables[key].append(
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
