"""LangGraph agent core for querygraph-agent.

Exposes the graph factory and concrete ``AgentService`` implementation built
on top of LangGraph's ``StateGraph`` with ``MemorySaver`` checkpointing.

Public API
----------
``create_graph``
    Assembles and compiles the LangGraph ``StateGraph`` for a given set of
    settings, executor and ownership store.

``GraphAgentService``
    Concrete ``AgentService`` implementation that wraps the compiled graph.

``AgentState``
    The LangGraph state type used by the graph.
"""

from querygraph_agent.agent.graph_factory import GraphAgentService, create_graph
from querygraph_agent.agent.state import AgentState

__all__ = [
    "AgentState",
    "GraphAgentService",
    "create_graph",
]
