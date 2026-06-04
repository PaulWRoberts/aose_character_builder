"""Other possessions — the cycle-free core for free-text "implied item" entries.

Each entry is a plain untracked string ("a bronze key"); no weight, value, or
encumbrance.  Mutators return new lists (no in-place mutation) and raise
``PossessionError`` on bad input; routes map it to HTTP 400.  Imports nothing
from the codebase; nothing imports it back.
"""
from __future__ import annotations


class PossessionError(ValueError):
    """Invalid other-possessions mutation (routes map to HTTP 400)."""


def add_possession(items: list[str], text: str) -> list[str]:
    """Return a new list with ``text`` (trimmed) appended.  Empty or
    whitespace-only input is ignored (the list is returned unchanged)."""
    text = text.strip()
    if not text:
        return list(items)
    return [*items, text]


def remove_possession(items: list[str], index: int) -> list[str]:
    """Return a new list with the entry at ``index`` removed.  An out-of-range
    index raises ``PossessionError``."""
    if index < 0 or index >= len(items):
        raise PossessionError(f"no possession at index {index}")
    return [*items[:index], *items[index + 1:]]
