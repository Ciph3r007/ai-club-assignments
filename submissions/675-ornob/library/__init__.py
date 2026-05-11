"""QueryGraph Agent — reusable multi-turn conversational query agent.

Import stable symbols from this package:

    from library import (
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

from library.agent.graph_factory import GraphAgentService, create_graph
from library.api.events import (
    AgentEvent,
    AssistantTextEvent,
    DbResultEvent,
    DoneEvent,
    ErrorEvent,
    ThinkingEvent,
)
from library.api.service import AgentService, SessionContext
from library.config.settings import Settings, get_settings
from library.db.query_executor import QueryExecutor
from library.db.sql_guard import SqlValidationRule
from library.exceptions import (
    ConfigurationError,
    ModelToolCallError,
    OwnershipError,
    QueryGraphError,
    SqlGuardError,
)
from library.registry.tool_registry import (
    ToolHandler,
    ToolRegistration,
    ToolRegistry,
    tool_registry,
)
from library.session.ownership import InMemoryOwnershipStore, OwnershipStore
from library.tools.error_mapper import ErrorMapper
from library.version import __version__

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
