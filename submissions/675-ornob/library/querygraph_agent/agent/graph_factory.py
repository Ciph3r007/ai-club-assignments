"""Graph factory and concrete ``AgentService`` implementation.

``create_graph``
    Builds and compiles a LangGraph ``StateGraph`` driven by ``tool_registry``:

    - Reads tool schemas, node names, and retry flags from
      ``tool_registry.all()`` - adding a new tool to the registry
      automatically wires it into the graph with zero changes here.
    - A ``call_model`` entry node that invokes the configured LLM backend.
    - Conditional routing to tool-handler nodes based on the last tool call.
    - ``MemorySaver`` checkpointer for in-process, per-thread conversation memory.

    Memory is **process-local** and resets when the process restarts.  For
    persistence across restarts, replace ``MemorySaver`` with a persistent
    checkpointer (e.g. ``SqliteSaver``, ``PostgresSaver``).

``GraphAgentService``
    Concrete ``AgentService`` that wraps the compiled graph, enforcing
    ownership checks and converting graph output to ``AgentEvent`` lists /
    async generators.

Event extraction
----------------
``_extract_events_from_state`` walks the current turn's ``ToolMessage`` objects
to surface ``DbResultEvent`` instances (serialized as JSON by ``run_sql_node``)
before appending the final ``AssistantTextEvent``.  Only messages produced
*after* the last ``HumanMessage`` are considered to avoid surfacing results
from previous turns.

Streaming
---------
``stream_turn`` uses ``astream_events(version="v2")`` which fires
``on_chat_model_stream`` events for every token the LLM emits, giving true
incremental output instead of waiting for the full response.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from functools import partial
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

import querygraph_agent.registry.builtin_tools  # noqa: F401  # Populate tool_registry with builtin tools
from querygraph_agent.agent.content import ai_message_to_text
from querygraph_agent.agent.nodes import (
    call_model_node,
    sql_repair_node,
    tool_node,
)
from querygraph_agent.agent.router import route_after_db_query, route_after_model
from querygraph_agent.agent.state import AgentState
from querygraph_agent.api.events import (
    AgentEvent,
    AssistantTextEvent,
    DbResultEvent,
    DoneEvent,
    ErrorEvent,
)
from querygraph_agent.api.service import AgentService, SessionContext
from querygraph_agent.config.settings import Settings
from querygraph_agent.db.query_executor import QueryExecutor
from querygraph_agent.model.ollama_client import OllamaClient
from querygraph_agent.registry.tool_registry import tool_registry
from querygraph_agent.session.ownership import OwnershipStore


def create_graph(
    settings: Settings,
    executor: QueryExecutor,
    *,
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph[Any]:
    """Create and compile a LangGraph agent graph driven by ``tool_registry``.

    Parameters
    ----------
    settings:
        Application settings (used for OllamaClient and system_prompt when
        *llm* is ``None``).
    executor:
        Database query executor injected into tool nodes.
    llm:
        Optional ``BaseChatModel`` to use as the LLM backend.  If ``None``,
        an ``OllamaClient`` is created from *settings*.  Pass any
        LangChain-compatible model (Claude, GPT-4, local llama.cpp, etc.).
    checkpointer:
        Optional LangGraph checkpointer for conversation memory persistence.
        If ``None``, an in-process ``MemorySaver`` is used (resets on restart).
        Pass ``SqliteSaver`` or ``PostgresSaver`` for durable persistence.
    """
    if llm is None:
        client = OllamaClient(settings=settings, tools=tool_registry.schemas())
        model_with_tools = client.bind_tools()
    else:
        model_with_tools = llm.bind_tools(tool_registry.schemas())

    _checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    builder: StateGraph[AgentState] = StateGraph(AgentState)
    builder.add_node(
        "call_model",
        partial(call_model_node, model=model_with_tools, system_prompt=settings.system_prompt),
    )
    builder.add_node("sql_repair_node", sql_repair_node)

    for reg in tool_registry.all():
        builder.add_node(
            reg.node_name,
            partial(tool_node, executor=executor, tool_name=reg.name),
        )
        if reg.has_retry:
            builder.add_conditional_edges(reg.node_name, route_after_db_query)
        else:
            builder.add_edge(reg.node_name, "call_model")

    builder.set_entry_point("call_model")
    builder.add_conditional_edges("call_model", route_after_model)
    builder.add_edge("sql_repair_node", "call_model")

    return builder.compile(checkpointer=_checkpointer)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_turn_tool_messages(messages: list[Any]) -> list[ToolMessage]:
    """Return only ToolMessages produced *after* the last HumanMessage.

    This prevents surfacing DB results from previous turns when the graph
    state accumulates message history across multiple ``run_turn`` calls.
    """
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i
    return [
        msg
        for msg in messages[last_human_idx + 1 :]
        if isinstance(msg, ToolMessage)
    ]


def _extract_events_from_state(state: dict[str, Any]) -> list[AgentEvent]:
    """Convert graph state to an ordered list of ``AgentEvent`` objects.

    Surfaces ``DbResultEvent`` instances from ToolMessages in the current turn
    (JSON-serialized by ``run_sql_node``) before appending the final
    ``AssistantTextEvent``.  Always ends with ``DoneEvent``.
    """
    events: list[AgentEvent] = []
    messages: list[Any] = state.get("messages", [])

    for tool_msg in _current_turn_tool_messages(messages):
        try:
            data = json.loads(tool_msg.content)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("type") == "db_result":
            events.append(DbResultEvent.model_validate(data))

    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            text = ai_message_to_text(last)
            if text:
                events.append(AssistantTextEvent(content=text))

    events.append(DoneEvent())
    return events


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GraphAgentService(AgentService):
    """Concrete ``AgentService`` backed by a compiled LangGraph graph."""

    def __init__(
        self,
        settings: Settings,
        executor: QueryExecutor,
        ownership_store: OwnershipStore,
        *,
        llm: BaseChatModel | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        self._graph: CompiledStateGraph[Any] = create_graph(
            settings, executor, llm=llm, checkpointer=checkpointer
        )
        self._ownership_store = ownership_store

    async def run_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> list[AgentEvent]:
        """Execute one conversational turn and return all events.

        Returns ``DbResultEvent`` objects for any queries executed during the
        turn, followed by ``AssistantTextEvent`` and always ends with
        ``DoneEvent``.  Ownership failure and graph exceptions are surfaced as
        ``ErrorEvent``; the method never raises.
        """
        err = self._check_ownership(session_context, self._ownership_store)
        if err is not None:
            return [err, DoneEvent()]

        run_config: RunnableConfig = {"configurable": {"thread_id": session_context.thread_id}}
        try:
            state = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=user_message)], "sql_retry_count": 0},
                config=run_config,
            )
        except Exception as exc:  # noqa: BLE001
            return [
                ErrorEvent(error_type=type(exc).__name__, message=str(exc)),
                DoneEvent(),
            ]

        return _extract_events_from_state(state)

    def stream_turn(
        self,
        session_context: SessionContext,
        user_message: str,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Execute one conversational turn and yield events as tokens arrive.

        Uses ``astream_events(version="v2")`` which fires
        ``on_chat_model_stream`` for every token, giving true incremental
        output.  Tool-call frames (where the model is constructing a function
        call, not writing final prose) are filtered out so only user-visible
        text is yielded.  Always ends with ``DoneEvent``.
        """

        async def _gen() -> AsyncGenerator[AgentEvent, None]:
            err = self._check_ownership(session_context, self._ownership_store)
            if err is not None:
                yield err
                yield DoneEvent()
                return

            stream_config: RunnableConfig = {
                "configurable": {"thread_id": session_context.thread_id}
            }
            try:
                async for event in self._graph.astream_events(
                    {"messages": [HumanMessage(content=user_message)], "sql_retry_count": 0},
                    config=stream_config,
                    version="v2",
                ):
                    if event["event"] != "on_chat_model_stream":
                        continue
                    chunk = event["data"]["chunk"]
                    if getattr(chunk, "tool_call_chunks", None):
                        continue  # model is building a tool call, not writing prose
                    content = chunk.content
                    if isinstance(content, str) and content:
                        yield AssistantTextEvent(content=content)
            except Exception as exc:  # noqa: BLE001
                yield ErrorEvent(error_type=type(exc).__name__, message=str(exc))

            yield DoneEvent()

        return _gen()


__all__ = [
    "GraphAgentService",
    "create_graph",
]
