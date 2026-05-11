"""Deterministic routing logic for the LangGraph agent graph.

`route_after_model` reads registered routes from `tool_registry` at
call time - no hardcoded tool-name mapping.  Adding a new tool to the
registry automatically makes it routable without editing this file.

`route_after_db_query` handles the SQL self-repair cycle and is a numeric
guard, not a dispatch table - kept as a plain conditional.
"""

from __future__ import annotations

from typing import Literal

from library.agent.state import AgentState

# Maximum consecutive SQL repair attempts before the LLM is asked to give up.
MAX_SQL_RETRIES: int = 3


def route_after_model(state: AgentState) -> str:
    """Route to the tool-handler node named by `tool_registry.routes()`.

    Returns `"__end__"` when there are no tool calls or the tool name is
    not registered.
    """
    # Import inside function to avoid circular imports at module load time.
    from library.registry.tool_registry import tool_registry

    last = state["messages"][-1]
    if not hasattr(last, "tool_calls") or not last.tool_calls:
        return "__end__"
    return tool_registry.routes().get(last.tool_calls[0]["name"], "__end__")


def route_after_db_query(
    state: AgentState,
) -> Literal["sql_repair_node", "call_model"]:
    """Route to self-repair when SQL failed and retries remain, else to `call_model`.

    `run_sql_node` increments `sql_retry_count` on every error and resets
    it to 0 on success, so `> 0` is a reliable signal that the last query
    failed.
    """
    retry_count: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
    if 0 < retry_count <= MAX_SQL_RETRIES:
        return "sql_repair_node"
    return "call_model"


__all__ = ["MAX_SQL_RETRIES", "route_after_db_query", "route_after_model"]
