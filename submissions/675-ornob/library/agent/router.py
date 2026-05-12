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
REPAIR_TURN_NAME: str = "repair"

_QUERY_ROUTE: dict[bool, Literal["sql_repair_node", "call_model"]] = {
    True: "sql_repair_node",
    False: "call_model",
}

_DB_TOOLS: frozenset[str] = frozenset({"run_sql", "db_schema"})


def route_after_model(state: AgentState, *, think_required: bool = False) -> str:
    """Route to the tool-handler node named by `tool_registry.routes()`.

    When `think_required=True`, intercepts DB tool calls that have not been
    preceded by a `think` call this turn and routes to `think_gate_node` first.

    Returns `"__end__"` when there are no tool calls or the tool name is
    not registered.
    """
    # Import inside function to avoid circular imports at module load time.
    from library.agent.tracing import current_turn_tool_call_names
    from library.registry.tool_registry import tool_registry

    last = state["messages"][-1]
    if not hasattr(last, "tool_calls") or not last.tool_calls:
        return "__end__"

    tool_name = last.tool_calls[0]["name"]

    if think_required and tool_name in _DB_TOOLS:
        if "think" not in current_turn_tool_call_names(state):
            return "think_gate_node"

    return tool_registry.routes().get(tool_name, "__end__")


def route_after_db_query(
    state: AgentState,
) -> Literal["sql_repair_node", "call_model"]:
    """Route to self-repair when SQL failed and retries remain, else to `call_model`.

    `run_sql_node` increments `sql_retry_count` on every error and resets
    it to 0 on success, so `> 0` is a reliable signal that the last query
    failed.
    """
    retry_count: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
    return _QUERY_ROUTE[0 < retry_count <= MAX_SQL_RETRIES]


__all__ = ["MAX_SQL_RETRIES", "REPAIR_TURN_NAME", "_DB_TOOLS", "route_after_db_query", "route_after_model"]
