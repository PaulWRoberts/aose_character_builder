"""Secondary-skill rolling (AOSE optional rule).

Cycle-free: imports only ``random`` and the ``SecondarySkillEntry`` model.
A table is a list of weighted entries; exactly one may be ``roll_twice``.
"""
import random as _random

from aose.models import SecondarySkillEntry


class SecondarySkillError(Exception):
    """Raised when a table cannot satisfy a roll (empty, or a roll-twice with
    fewer than two real trades to draw from)."""


def selectable_names(entries: list[SecondarySkillEntry]) -> list[str]:
    """Trade names a player may hand-pick — excludes the roll-twice entry."""
    return [e.name for e in entries if not e.roll_twice]


def _weighted_pick(
    entries: list[SecondarySkillEntry], rng: _random.Random
) -> SecondarySkillEntry:
    total = sum(e.weight for e in entries)
    r = rng.randint(1, total)
    upto = 0
    for e in entries:
        upto += e.weight
        if r <= upto:
            return e
    return entries[-1]  # unreachable with positive integer weights


def roll(
    entries: list[SecondarySkillEntry],
    rng: _random.Random | None = None,
) -> list[str]:
    """Weighted pick over the table.  A normal pick returns ``[trade]``; the
    roll-twice outcome expands to two distinct real trades (never nesting).
    Raises ``SecondarySkillError`` on an empty table or a roll-twice that cannot
    draw two distinct trades."""
    _rng = rng or _random.Random()
    if not entries:
        raise SecondarySkillError("No secondary skills configured.")
    picked = _weighted_pick(entries, _rng)
    if not picked.roll_twice:
        return [picked.name]
    if len(selectable_names(entries)) < 2:
        raise SecondarySkillError(
            "Roll-for-two needs at least two real trades in the table."
        )
    chosen: list[str] = []
    while len(chosen) < 2:
        e = _weighted_pick(entries, _rng)
        if e.roll_twice or e.name in chosen:
            continue
        chosen.append(e.name)
    return chosen
