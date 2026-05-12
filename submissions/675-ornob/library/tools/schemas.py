"""LangChain tool schemas for the querygraph-agent.

Defines the Pydantic input models and StructuredTool instances that are bound
to the Ollama model via `model.bind_tools([think_tool, run_sql_tool, db_schema_tool])`.

Tool names are stable identifiers used by the LangGraph router:
- `"think"`     - internal reasoning step before answering
- `"run_sql"`   - execute a read-only SQL SELECT query
- `"db_schema"` - inspect table/column metadata from the database

Handler implementations live in `tools/think.py`, `tools/db_query.py`,
and `tools/db_schema.py`; these schema objects are what the model layer
uses for tool-call parsing.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ThinkInput(BaseModel):
    """Input schema for the think tool."""

    thought: str = Field(..., description="Internal reasoning step")


class RunSqlInput(BaseModel):
    """Input schema for the run_sql tool."""

    query: str = Field(..., description="SQL SELECT query to execute")


class DbSchemaInput(BaseModel):
    """Input schema for the db_schema tool."""

    table_name: str | None = Field(
        default=None,
        description="Table name to inspect. Omit to list all tables.",
    )


# ---------------------------------------------------------------------------
# Schema stubs
#
# The @tool decorator creates StructuredTool objects that describe tools to
# the LLM (name, description, args_schema). The function body is never called
# by LangGraph — execution is routed to the handler registered in tool_registry.
# Direct invocation raises NotImplementedError to surface misuse immediately.
# ---------------------------------------------------------------------------

@tool("think", args_schema=ThinkInput, return_direct=False)
def think_tool(thought: str) -> str:
    """Use this tool for internal reasoning steps before answering."""
    raise NotImplementedError("Schema stub — use tool_registry or AgentService, not direct call")


@tool("run_sql", args_schema=RunSqlInput, return_direct=False)
def run_sql_tool(query: str) -> str:
    """Execute a read-only SQL SELECT query against the database."""
    raise NotImplementedError("Schema stub — use tool_registry or AgentService, not direct call")


@tool("db_schema", args_schema=DbSchemaInput, return_direct=False)
def db_schema_tool(table_name: str | None = None) -> str:
    """Inspect table and column metadata from the database schema."""
    raise NotImplementedError("Schema stub — use tool_registry or AgentService, not direct call")


__all__ = [
    "RunSqlInput",
    "DbSchemaInput",
    "ThinkInput",
    "run_sql_tool",
    "db_schema_tool",
    "think_tool",
]
