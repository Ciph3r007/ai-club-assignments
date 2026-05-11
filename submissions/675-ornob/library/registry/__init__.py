"""Tool registry package.

Import `tool_registry` from this package to access the module-level
singleton.  Import `builtin_tools` to ensure the built-in tools are
registered before building the graph.
"""
from library.registry.tool_registry import (
    ToolHandler,
    ToolRegistration,
    ToolRegistry,
    tool_registry,
)

__all__ = ["ToolHandler", "ToolRegistration", "ToolRegistry", "tool_registry"]
