# src/library/agent/nodes.py
"""LangGraph node implementations for the querygraph-agent graph.

All tool-handling nodes are generated via the generic `tool_node` factory
function, which resolves the handler from `tool_registry` at invocation time.
Per-tool node functions (`think_node`, `run_sql_node`, `db_schema_node`)
are removed - `graph_factory` uses `partial(tool_node, executor=executor, tool_name=...)`
instead.

`sql_repair_node` is NOT a tool node - it injects a repair prompt and is
always registered explicitly in the graph.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage

from library.agent.router import MAX_SQL_RETRIES, REPAIR_TURN_NAME
from library.agent.state import AgentState
from library.db.query_executor import QueryExecutor
from library.registry.tool_registry import ToolRegistry, tool_registry

# ---------------------------------------------------------------------------
# Tool content serialization dispatch
# ---------------------------------------------------------------------------

_TOOL_CONTENT_EXTRACTORS: dict[str, Callable[[Any], str]] = {
    "thinking": lambda e: e.content,
    "assistant_text": lambda e: e.content,
}


def _to_tool_content(event: Any) -> str:
    """Serialize an agent event to a string for a `ToolMessage`.

    Known types (thinking, assistant_text) extract `.content` directly.
    All other event types fall back to full JSON via `model_dump_json()`.
    """
    extractor = _TOOL_CONTENT_EXTRACTORS.get(event.type)
    return extractor(event) if extractor else event.model_dump_json()


# ---------------------------------------------------------------------------
# Ollama tool-call fallback parser
# ---------------------------------------------------------------------------

_TOOL_CALL_FENCE_PATTERNS: tuple[str, ...] = (
    r"``json\s*([\s\S]*?)``",
    r"``\s*([\s\S]*?)``",
)


def _extract_json_objects(text: str) -> list[str]:
    """Extract every brace-balanced JSON object from text."""
    objects: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                objects.append(text[start : i + 1])
                start = -1
    return objects


def _try_parse_tool_call_from_text(content: str) -> list[dict[str, Any]] | None:
    """Parse a JSON tool-call that Ollama embedded in response text."""
    candidates: list[str] = []
    for pattern in _TOOL_CALL_FENCE_PATTERNS:
        for match in re.finditer(pattern, content, re.DOTALL):
            candidates.append(match.group(1).strip())
    candidates.extend(_extract_json_objects(content))

    known_names = frozenset(tool_registry.routes().keys())
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if name not in known_names:
            continue
        args = data.get("arguments", data.get("args", {}))
        if not isinstance(args, dict):
            continue  # malformed args — skip this candidate, try the next
        return [{"id": f"call_{uuid.uuid4().hex[:8]}", "name": name, "args": args, "type": "tool_call"}]

    return None


# ---------------------------------------------------------------------------
# SQL repair message dispatch
# ---------------------------------------------------------------------------

_REPAIR_MESSAGES: dict[bool, Callable[[int, int], str]] = {
    False: lambda n, max_: (
        f"[SQL repair - attempt {n}/{max_}] The previous SQL query failed. "
        "Review the error above, use the db_schema tool if you need to verify "
        "column names or types, then retry with a corrected SQL query."
    ),
    True: lambda _n, _max: (
        "All SQL retry attempts have been exhausted. Please explain the issue "
        "clearly to the user and suggest next steps."
    ),
}

_NEXT_RETRY_COUNT: dict[str, Callable[[int], int]] = {
    "error": lambda n: n + 1,
}

_RETRY_COUNT_UPDATES: dict[bool, Callable[[int, str], dict[str, Any]]] = {
    True: lambda current, event_type: {
        "sql_retry_count": _NEXT_RETRY_COUNT.get(event_type, lambda _: 0)(current)
    },
    False: lambda _c, _e: {},
}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _repair_ollama_response(response: Any) -> Any:
    """Return a repaired AIMessage if Ollama embedded tool-call JSON in response text."""
    if getattr(response, "tool_calls", None) or not isinstance(response.content, str):
        return response
    parsed = _try_parse_tool_call_from_text(response.content)
    return AIMessage(content="", tool_calls=parsed) if parsed else response


async def call_model_node(
    state: AgentState,
    model: BaseChatModel,
    system_prompt: str,
    max_context_messages: int,
) -> dict[str, Any]:
    """Invoke the LLM; inject system prompt; apply Ollama fallback parser.

    Trims the message history to the last `max_context_messages` before
    sending to the model — state retains the full history for tracing.
    """
    history = state["messages"][-max_context_messages:]
    response = await model.ainvoke([SystemMessage(content=system_prompt), *history])
    return {"messages": [_repair_ollama_response(response)]}


async def tool_node(
    state: AgentState,
    executor: QueryExecutor,
    tool_name: str,
    *,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Generic tool execution node - resolves handler from `tool_registry`.

    Pass registry in tests to avoid patching the module-level singleton.
    `graph_factory` creates partials without registry so they use the global.
    """
    _registry = registry if registry is not None else tool_registry
    last = state["messages"][-1]
    if not isinstance(last, AIMessage):
        raise TypeError(f"{tool_name}_node: expected AIMessage, got {type(last).__name__}")

    tool_call = last.tool_calls[0]
    handler = _registry.handler(tool_name)
    event = await handler.handle(executor, **tool_call["args"])
    tool_msg = ToolMessage(content=_to_tool_content(event), tool_call_id=tool_call["id"])

    reg = _registry.get(tool_name)
    current: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
    extra = _RETRY_COUNT_UPDATES[reg.has_retry](current, event.type)
    return {"messages": [tool_msg], **extra}


async def think_gate_node(state: AgentState) -> dict[str, Any]:
    """Inject a synthetic think step before the pending DB tool call.

    Removes the model's AIMessage (which called a DB tool without thinking first),
    inserts a think AIMessage + ToolMessage, then re-appends the original DB tool
    AIMessage so it remains last and tool_node can read it normally.
    """
    last = state["messages"][-1]
    tool_call = last.tool_calls[0]

    thought = (
        f"I need to call {tool_call['name']} with args {tool_call['args']}. "
        "Let me reason about the query before proceeding."
    )
    think_id = f"call_{uuid.uuid4().hex[:8]}"
    think_ai = AIMessage(
        content="",
        tool_calls=[{"id": think_id, "name": "think", "args": {"thought": thought}, "type": "tool_call"}],
    )
    think_tm = ToolMessage(content=thought, tool_call_id=think_id)
    db_ai = AIMessage(content=last.content, tool_calls=last.tool_calls)

    return {"messages": [RemoveMessage(id=last.id), think_ai, think_tm, db_ai]}


async def sql_repair_node(state: AgentState) -> dict[str, Any]:
    """Inject a targeted repair prompt so the LLM can self-correct failed SQL."""
    retry_count: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
    content = _REPAIR_MESSAGES[retry_count > MAX_SQL_RETRIES](retry_count, MAX_SQL_RETRIES)
    return {"messages": [HumanMessage(content=content, name=REPAIR_TURN_NAME)]}


__all__ = [
    "call_model_node",
    "sql_repair_node",
    "think_gate_node",
    "tool_node",
]
