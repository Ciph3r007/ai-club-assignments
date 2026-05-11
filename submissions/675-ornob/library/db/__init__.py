"""Database safety layer for library.

Provides read-only query execution with SQL validation, row limits, and
timeout enforcement.
"""

from library.db.query_executor import QueryExecutor, QueryResult
from library.db.sql_guard import validate_sql

__all__ = [
    "QueryExecutor",
    "QueryResult",
    "validate_sql",
]
