"""QueryGraph Agent - reusable multi-turn conversational query agent.

Public API
----------
Import the stable symbols from this module::

    from querygraph_agent import (
        # Service contract
        AgentService, GraphAgentService, create_graph, SessionContext,
        # Events
        AgentEvent, ThinkingEvent, AssistantTextEvent,
        DbResultEvent, DoneEvent, ErrorEvent,
        # Exceptions
        QueryGraphError, OwnershipError, SqlGuardError,
        ModelToolCallError, ConfigurationError,
        # Config
        Settings, get_settings,
        # DB
        QueryExecutor,
        # Ownership
        OwnershipStore, InMemoryOwnershipStore,
        # Extension points
        ToolHandler, ToolRegistration, ToolRegistry, tool_registry,
        SqlValidationRule, ErrorMapper,
    )
"""

from querygraph_agent.agent.graph_factory import GraphAgentService, create_graph
from querygraph_agent.api.events import (
    AgentEvent,
    AssistantTextEvent,
    DbResultEvent,
    DoneEvent,
    ErrorEvent,
    ThinkingEvent,
)
from querygraph_agent.api.service import AgentService, SessionContext
from querygraph_agent.config.settings import Settings, get_settings
from querygraph_agent.db.query_executor import QueryExecutor
from querygraph_agent.db.sql_guard import SqlValidationRule
from querygraph_agent.exceptions import (
    ConfigurationError,
    ModelToolCallError,
    OwnershipError,
    QueryGraphError,
    SqlGuardError,
)
from querygraph_agent.registry.tool_registry import (
    ToolHandler,
    ToolRegistration,
    ToolRegistry,
    tool_registry,
)
from querygraph_agent.session.ownership import InMemoryOwnershipStore, OwnershipStore
from querygraph_agent.tools.error_mapper import ErrorMapper
from querygraph_agent.version import __version__

__all__ = [
    "__version__",
    # Service contract
    "AgentService",
    "GraphAgentService",
    "create_graph",
    "SessionContext",
    # Events
    "AgentEvent",
    "AssistantTextEvent",
    "DbResultEvent",
    "DoneEvent",
    "ErrorEvent",
    "ThinkingEvent",
    # Exceptions
    "ConfigurationError",
    "ModelToolCallError",
    "OwnershipError",
    "QueryGraphError",
    "SqlGuardError",
    # Config
    "Settings",
    "get_settings",
    # DB
    "QueryExecutor",
    # Ownership
    "InMemoryOwnershipStore",
    "OwnershipStore",
    # Extension points
    "ErrorMapper",
    "SqlValidationRule",
    "ToolHandler",
    "ToolRegistration",
    "ToolRegistry",
    "tool_registry",
]
