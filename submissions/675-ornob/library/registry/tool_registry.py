"""ToolRegistry - central registry for agent tools.

Decouples graph construction from tool definitions.  ``graph_factory`` reads
``tool_registry.schemas()`` and ``tool_registry.all()`` instead of maintaining
a hardcoded list of tools.

Extension pattern::

    from library.registry.tool_registry import tool_registry, ToolRegistration
    from library import ToolHandler

    class MyHandler:
        async def handle(self, executor, **kwargs):
            ...

    tool_registry.register(ToolRegistration(
        name="my_tool",
        schema=my_langchain_tool,
        handler=MyHandler(),
        node_name="my_tool_node",
    ))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, runtime_checkable

from typing_extensions import Protocol

from library.exceptions import ConfigurationError

if TYPE_CHECKING:
    from library.api.events import AgentEvent
    from library.db.query_executor import QueryExecutor


@runtime_checkable
class ToolHandler(Protocol):
    """Protocol for all tool handler classes.

    Implement this to create a custom tool handler.  The ``executor`` parameter
    is always passed; handlers that do not need DB access accept and ignore it.
    All arguments from the LLM tool call are forwarded as ``**kwargs``.
    """

    async def handle(self, executor: QueryExecutor, **kwargs: Any) -> AgentEvent:
        """Execute the tool and return a typed ``AgentEvent``."""
        ...


@dataclass(frozen=True)
class ToolRegistration:
    """Immutable record binding a tool name to its schema, handler, and graph node.

    Parameters
    ----------
    name:
        Must match the ``@tool("name")`` string in the LangChain schema.
    schema:
        LangChain ``StructuredTool`` instance bound to the model.
    handler:
        ``ToolHandler`` instance invoked when the LLM calls this tool.
    node_name:
        Name of the LangGraph node that will execute this tool.
    has_retry:
        When ``True``, the graph wires a conditional edge from this node to
        ``sql_repair_node`` on execution error.  Default ``False``.
    """

    name: str
    schema: Any  # StructuredTool - avoid importing langchain at dataclass definition time
    handler: ToolHandler
    node_name: str
    has_retry: bool = False


class ToolRegistry:
    """Central registry for agent tools.

    Populated by ``registry/builtin_tools.py`` at import time.  The registry
    is read-only after startup - call ``register`` before ``create_graph``.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}

    def register(self, registration: ToolRegistration) -> None:
        """Register a tool.  Overwrites any existing registration for the same name."""
        self._tools[registration.name] = registration

    def schemas(self) -> list[Any]:
        """Return all LangChain tool schemas for binding to the model."""
        return [r.schema for r in self._tools.values()]

    def routes(self) -> dict[str, str]:
        """Return ``{tool_name: node_name}`` - used by the LangGraph router."""
        return {name: r.node_name for name, r in self._tools.items()}

    def handler(self, name: str) -> ToolHandler:
        """Return the handler for *name*.

        Raises ``ConfigurationError`` if the tool is not registered.
        """
        if name not in self._tools:
            raise ConfigurationError(
                f"No handler registered for tool '{name}'. "
                "Did you forget to import registry.builtin_tools?"
            )
        return self._tools[name].handler

    def get(self, name: str) -> ToolRegistration:
        """Return the full ``ToolRegistration`` for *name*.

        Raises ``ConfigurationError`` if the tool is not registered.
        """
        if name not in self._tools:
            raise ConfigurationError(f"No registration found for tool '{name}'.")
        return self._tools[name]

    def node_names(self) -> list[str]:
        """Return all registered node names."""
        return [r.node_name for r in self._tools.values()]

    def all(self) -> list[ToolRegistration]:
        """Return all registrations in insertion order."""
        return list(self._tools.values())


# Module-level singleton - populated by registry/builtin_tools.py
tool_registry = ToolRegistry()

__all__ = ["ToolHandler", "ToolRegistration", "ToolRegistry", "tool_registry"]
