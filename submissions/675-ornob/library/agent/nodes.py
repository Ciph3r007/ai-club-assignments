# src/library/agent/nodes.py
"""LangGraph node implementations for the querygraph-agent graph.

All tool-handling nodes are generated via the generic ``tool_node`` factory
function, which resolves the handler from ``tool_registry`` at invocation time.
Per-tool node functions (``think_node``, ``run_sql_node``, ``db_schema_node``)
are removed - ``graph_factory`` uses ``partial(tool_node, executor=executor, tool_name=...)``
instead.

``sql_repair_node`` is NOT a tool node - it injects a repair prompt and is
always registered explicitly in the graph.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from library.agent.router import MAX_SQL_RETRIES
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
    """Serialize an agent event to a string for a ``ToolMessage``."""
    extractor = _TOOL_CONTENT_EXTRACTORS.get(event.type)
    return extractor(event) if extractor else event.model_dump_json()


# ---------------------------------------------------------------------------
# Ollama tool-call fallback parser
# ---------------------------------------------------------------------------

_TOOL_CALL_FENCE_PATTERNS: tuple[str, ...] = (
    r"```json\s*([\s\S]*?)```",
    r"```\s*([\s\S]*?)```",
)


def _extract_json_objects(text: str) -> list[str]:
    """Extract every brace-balanced JSON object from *text*."""
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

_REPAIR_MESSAGES: dict[bool, str] = {
    True: "All SQL retry attempts have been exhausted. Please explain the issue clearly to the user and suggest next steps.",
    False: "[SQL repair - attempt {n}/{max}] The previous SQL query failed. Review the error above, use the db_schema tool if you need to verify column names or types, then retry with a corrected SQL query.",
}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def call_model_node(
    state: AgentState,
    model: BaseChatModel,
    system_prompt: str,
) -> dict[str, Any]:
    """Invoke the LLM; inject system prompt; apply Ollama fallback parser."""
    messages = [SystemMessage(content=system_prompt), *state["messages"]]
    response = await model.ainvoke(messages)

    if not getattr(response, "tool_calls", None) and isinstance(response.content, str):
        parsed = _try_parse_tool_call_from_text(response.content)
        if parsed:
            response = AIMessage(content="", tool_calls=parsed)

    return {"messages": [response]}


async def tool_node(
    state: AgentState,
    executor: QueryExecutor,
    tool_name: str,
    *,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Generic tool execution node - resolves handler from ``tool_registry``.

    Pass *registry* in tests to avoid patching the module-level singleton.
    ``graph_factory`` creates partials without *registry* so they use the global.
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
    if reg.has_retry:
        current: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
        new_count = (current + 1) if event.type == "error" else 0
        return {"messages": [tool_msg], "sql_retry_count": new_count}

    return {"messages": [tool_msg]}


async def sql_repair_node(state: AgentState) -> dict[str, Any]:
    """Inject a targeted repair prompt so the LLM can self-correct failed SQL."""
    retry_count: int = state.get("sql_retry_count", 0)  # type: ignore[assignment]
    template = _REPAIR_MESSAGES[retry_count > MAX_SQL_RETRIES]
    content = (
        template
        if "{n}" not in template
        else template.format(n=retry_count, max=MAX_SQL_RETRIES)
    )
    return {"messages": [HumanMessage(content=content, name="repair")]}


__all__ = [
    "call_model_node",
    "sql_repair_node",
    "tool_node",
]
