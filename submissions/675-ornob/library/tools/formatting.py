"""Human-friendly text formatting for agent events.

All functions return plain strings so callers decide how to render them
(print, log, write to a stream, etc.).  No external dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from library.api.events import DbResultEvent


def format_db_result(event: DbResultEvent) -> str:
    """Format a DbResultEvent as a labelled ASCII table.

    Output example:

        SQL: SELECT * FROM customers LIMIT 5
        Rows returned: 5

        customer_id  company_name           contact_name
        -----------  ---------------------  ------------
        1            Alfreds Futterkiste    Maria Anders

    Returns:
        str: A newline-terminated string. When there are no rows, returns
            a short "(no rows returned)" notice instead of a table.
    """
    lines: list[str] = [
        f"SQL: {event.sql}",
        f"Rows returned: {event.row_count}",
    ]

    if not event.rows:
        lines.append("(no rows returned)")
        return "\n".join(lines) + "\n"

    columns = list(event.rows[0].keys())
    col_widths = [
        max(len(col), max((len(str(row.get(col, ""))) for row in event.rows), default=0))
        for col in columns
    ]

    header = "  ".join(col.ljust(w) for col, w in zip(columns, col_widths))
    separator = "  ".join("-" * w for w in col_widths)

    lines.append("")
    lines.append(header)
    lines.append(separator)
    for row in event.rows:
        lines.append("  ".join(str(row.get(col, "")).ljust(w) for col, w in zip(columns, col_widths)))

    return "\n".join(lines) + "\n"


_EVENT_PRINTERS: dict[str, Any] = {
    "assistant_text": lambda e: print(f"Agent: {e.content}"),
    "db_result": lambda e: print(format_db_result(e)),
    "thinking": lambda e: print(f"[thinking] {e.content}"),
    "error": lambda e: print(f"[error/{e.error_type}] {e.message}"),
}

_STREAM_PRINTERS: dict[str, Any] = {
    "assistant_text": lambda e: print(e.content, end="", flush=True),
    "done": lambda e: print(),
    "error": lambda e: print(f"\n[error/{e.error_type}] {e.message}"),
}


def print_events(events: Iterable[Any]) -> None:
    """Print each event in *events* using a human-readable format."""
    for event in events:
        printer = _EVENT_PRINTERS.get(event.type)
        if printer:
            printer(event)


def print_stream_event(event: Any) -> None:
    """Print a single streaming event token as it arrives."""
    printer = _STREAM_PRINTERS.get(event.type)
    if printer:
        printer(event)


__all__ = ["format_db_result", "print_events", "print_stream_event"]
