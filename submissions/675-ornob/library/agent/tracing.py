# library/agent/tracing.py
"""Graph state inspection utilities for tracing agent tool-call sequences."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage


def current_turn_messages(state: dict[str, Any]) -> list[Any]:
    """Return messages produced in the current turn.

    `state["messages"]` accumulates the full thread history via the
    `add_messages` reducer.  This returns the slice starting after the last
    user-originated `HumanMessage` (i.e. the most recent turn boundary).

    Repair prompts injected by `sql_repair_node` use `name="repair"` and
    are skipped so the boundary stays at the original user input.
    """
    msgs: list[Any] = state.get("messages", [])
    last_user_idx = max(
        (
            i
            for i, m in enumerate(msgs)
            if isinstance(m, HumanMessage) and getattr(m, "name", None) != "repair"
        ),
        default=-1,
    )
    return msgs[last_user_idx + 1 :]


def tool_call_names(messages: list[Any]) -> list[str]:
    """Return ordered tool-call names from messages.

    Collects the `name` field from every tool call on every `AIMessage`
    in messages, preserving invocation order.
    """
    names: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                if name := tc.get("name"):
                    names.append(name)
    return names


def current_turn_tool_call_names(state: dict[str, Any]) -> list[str]:
    """Return ordered tool-call names produced in the current turn."""
    return tool_call_names(current_turn_messages(state))


__all__ = ["current_turn_messages", "current_turn_tool_call_names", "tool_call_names"]
