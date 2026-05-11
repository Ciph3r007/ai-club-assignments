"""LangGraph agent state definition.

``AgentState`` extends ``MessagesState`` (which provides the
``messages: Annotated[list[BaseMessage], add_messages]`` field) with any
extra fields required by the querygraph-agent graph.

The ``add_messages`` reducer appended by ``MessagesState`` ensures that each
graph node can return ``{"messages": [...new messages...]}`` and LangGraph
will *append* those messages to the running list rather than replacing it,
giving the agent its message history.
"""

from __future__ import annotations

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Graph state for the querygraph-agent ReAct-style loop.

    Inherits from ``MessagesState``:
    - ``messages: Annotated[list[BaseMessage], add_messages]``

    ``sql_retry_count`` tracks consecutive SQL execution failures within a
    single turn so the graph can route to the self-repair node without
    looping forever.  Reset to 0 at the start of every ``run_turn`` call.
    """

    sql_retry_count: int


__all__ = ["AgentState"]
