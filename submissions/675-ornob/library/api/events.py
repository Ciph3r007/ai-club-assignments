"""Typed event models for agent stream and non-stream outputs.

All events are `pydantic.BaseModel` subclasses with a `type` literal field
that acts as a discriminator.  Callers can use `isinstance` checks or pattern
match on `event.type` to handle each variant.

Event taxonomy
--------------
ThinkingEvent
    Internal reasoning emitted while the agent is working.  Should not be
    shown verbatim to end users in production but is useful for debugging and
    transparency UIs.

AssistantTextEvent
    A finalized natural-language response from the agent.

DbResultEvent
    The result of a SQL query executed by the agent, including the SQL text
    and the rows returned.

DoneEvent
    Signals that the turn is complete.  Always the last event in a stream.

ErrorEvent
    A typed error that occurred during the turn.  The `error_type` field
    maps to one of the `QueryGraphError` subclass names so callers can
    branch without catching exceptions.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _BaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


class ThinkingEvent(_BaseEvent):
    """Agent reasoning / chain-of-thought fragment."""

    type: Literal["thinking"] = "thinking"
    content: str = Field(..., description="Raw reasoning text from the model.")


class AssistantTextEvent(_BaseEvent):
    """Final natural-language answer produced by the agent."""

    type: Literal["assistant_text"] = "assistant_text"
    content: str = Field(..., description="Human-readable response text.")


class DbResultEvent(_BaseEvent):
    """Result of a SQL query executed by the agent."""

    type: Literal["db_result"] = "db_result"
    sql: str = Field(..., description="The SQL statement that was executed.")
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows returned by the query as a list of column->value dicts.",
    )
    row_count: int = Field(0, description="Total number of rows returned.")

    @model_validator(mode="after")
    def _set_row_count(self) -> DbResultEvent:
        object.__setattr__(self, "row_count", len(self.rows))
        return self


class DoneEvent(_BaseEvent):
    """Sentinel event marking end-of-turn.  Always the final event in a stream."""

    type: Literal["done"] = "done"


class ErrorEvent(_BaseEvent):
    """Typed error that occurred during the turn.

    `error_type` is the short class name of the underlying domain exception
    (e.g. `"ModelToolCallError"`, `"SqlGuardError"`).  When the error
    originates outside the domain hierarchy, `error_type` is `"UnknownError"`.
    """

    type: Literal["error"] = "error"
    error_type: str = Field(
        ...,
        description="Short name of the domain exception class, e.g. 'ModelToolCallError'.",
    )
    message: str = Field(..., description="Human-readable description of the error.")


# Union type for exhaustive event handling, with a discriminator on the `type`
# field for efficient and unambiguous parsing.
AgentEvent = Annotated[
    ThinkingEvent | AssistantTextEvent | DbResultEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]

__all__ = [
    "AgentEvent",
    "AssistantTextEvent",
    "DbResultEvent",
    "DoneEvent",
    "ErrorEvent",
    "ThinkingEvent",
]
