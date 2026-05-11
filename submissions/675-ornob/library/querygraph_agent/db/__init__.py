"""Database safety layer for querygraph_agent.

Provides read-only query execution with SQL validation, row limits, and
timeout enforcement.
"""

from querygraph_agent.db.query_executor import QueryExecutor, QueryResult
from querygraph_agent.db.sql_guard import validate_sql

__all__ = [
    "QueryExecutor",
    "QueryResult",
    "validate_sql",
]
