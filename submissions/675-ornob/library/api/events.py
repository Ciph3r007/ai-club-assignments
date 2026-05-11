"""Typed event models for agent outputs.

All events are Pydantic BaseModel subclasses. Branch on `event.type` or use
isinstance checks to handle each variant.

Event types:
    ThinkingEvent: Internal reasoning while the agent is working.
    AssistantTextEvent: Final natural-language response from the agent.
    DbResultEvent: SQL query result including the sql text and rows returned.
    DoneEvent: Always the last event — signals end of turn.
    ErrorEvent: Typed error mapped to a QueryGraphError subclass name.
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
