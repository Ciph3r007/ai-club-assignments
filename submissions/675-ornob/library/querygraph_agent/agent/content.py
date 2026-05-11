"""AIMessage content extraction.

Replaces the ``isinstance(content, str) / isinstance(content, list)`` chain
in ``graph_factory.py`` with a type-keyed dispatch dict.  Adding support for
a new content shape = one new entry in ``_CONTENT_EXTRACTORS``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_CONTENT_EXTRACTORS: dict[type, Callable[[Any], str]] = {
    str: lambda c: c,
    list: lambda c: "".join(
        p.get("text", "") if isinstance(p, dict) else str(p) for p in c
    ).strip(),
}


def ai_message_to_text(msg: Any) -> str:
    """Extract plain text from an ``AIMessage``-like object.

    Handles ``str`` content (common case) and the list-of-dicts format that
    some models (e.g. Claude) return.  Returns ``""`` for unknown types or
    missing ``content`` attribute.
    """
    content = getattr(msg, "content", "")
    extractor = _CONTENT_EXTRACTORS.get(type(content))
    return extractor(content) if extractor else ""


__all__ = ["ai_message_to_text"]
