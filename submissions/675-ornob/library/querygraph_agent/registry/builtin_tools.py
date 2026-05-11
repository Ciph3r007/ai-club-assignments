"""Register the built-in tools into the module-level ``tool_registry`` singleton.

Import this module once before calling ``create_graph`` to ensure all built-in
tools are available.  ``graph_factory.py`` imports it automatically - external
callers do not need to import it directly unless they are bypassing the factory.

Registration is idempotent - re-importing this module overwrites the same keys.
"""

from __future__ import annotations

from querygraph_agent.registry.tool_registry import ToolRegistration, tool_registry
from querygraph_agent.tools.db_query import RunSqlHandler
from querygraph_agent.tools.db_schema import DbSchemaHandler
from querygraph_agent.tools.schemas import db_schema_tool, run_sql_tool, think_tool
from querygraph_agent.tools.think import ThinkHandler

tool_registry.register(
    ToolRegistration(
        name="think",
        schema=think_tool,
        handler=ThinkHandler(),
        node_name="think_node",
        has_retry=False,
    )
)
tool_registry.register(
    ToolRegistration(
        name="run_sql",
        schema=run_sql_tool,
        handler=RunSqlHandler(),
        node_name="run_sql_node",
        has_retry=True,
    )
)
tool_registry.register(
    ToolRegistration(
        name="db_schema",
        schema=db_schema_tool,
        handler=DbSchemaHandler(),
        node_name="db_schema_node",
        has_retry=False,
    )
)

__all__ = []
