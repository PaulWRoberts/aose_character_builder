"""Spell engine — the cycle-free core for spell access, known/prepared sets,
and spellbook/prepared mutations.

Imports only models + the data loader (like ``engine/magic.py``); no derivation
module imports it back.  Arcane vs divine is read from the SpellList registry,
not the class.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.models import CharClass, ClassEntry, ClassLevelData, RuleSet, Spell

CasterType = Literal["arcane", "divine"]


class SpellError(ValueError):
    """Base for all spell access / mutation errors (routes map to HTTP 400)."""


# ── Derivation / queries ──────────────────────────────────────────────────

def caster_type_of(cls: CharClass, data: GameData) -> CasterType | None:
    """The common caster type of the class's referenced spell lists.

    Returns None for a non-caster (no spell_lists).  Raises if a referenced
    list is unknown, or if the class mixes arcane and divine lists (AOSE has
    no such class)."""
    if not cls.spell_lists:
        return None
    types: set[CasterType] = set()
    for list_id in cls.spell_lists:
        sl = data.spell_lists.get(list_id)
        if sl is None:
            raise SpellError(f"{cls.id!r} references unknown spell list {list_id!r}")
        types.add(sl.caster_type)
    if len(types) > 1:
        raise SpellError(f"{cls.id!r} mixes arcane and divine spell lists")
    return next(iter(types))


def _level_row(entry: ClassEntry, cls: CharClass) -> ClassLevelData | None:
    return cls.progression.get(entry.level)


def accessible_levels(entry: ClassEntry, cls: CharClass) -> set[int]:
    """Spell levels the class can cast at the entry's level (has >=1 slot)."""
    row = _level_row(entry, cls)
    if row is None or not row.spell_slots:
        return set()
    return {lvl for lvl, n in row.spell_slots.items() if n > 0}


def memorizable_slots(entry: ClassEntry, cls: CharClass) -> dict[int, int]:
    """spell-level -> slot count at the entry's level.  Prepared cap, and (under
    standard rules) the per-level spellbook size.  Empty if no casting yet."""
    row = _level_row(entry, cls)
    if row is None or not row.spell_slots:
        return {}
    return dict(row.spell_slots)


def _on_class_lists(spell: Spell, cls: CharClass) -> bool:
    return bool(set(spell.spell_lists) & set(cls.spell_lists))


def known_spells(entry: ClassEntry, cls: CharClass, data: GameData) -> list[Spell]:
    """Spells the character knows.

    arcane: the resolved spellbook (in stored order).
    divine: every spell on the class's lists at an accessible level (by level,name).
    """
    ctype = caster_type_of(cls, data)
    if ctype == "arcane":
        return [data.spells[s] for s in entry.spellbook if s in data.spells]
    if ctype == "divine":
        levels = accessible_levels(entry, cls)
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.level in levels),
            key=lambda s: (s.level, s.name),
        )
    return []


def learnable_spells(entry: ClassEntry, cls: CharClass, data: GameData) -> list[Spell]:
    """Arcane-only: accessible-level spells on the class's lists not yet known."""
    if caster_type_of(cls, data) != "arcane":
        return []
    levels = accessible_levels(entry, cls)
    known = set(entry.spellbook)
    return sorted(
        (s for s in data.spells.values()
         if _on_class_lists(s, cls) and s.level in levels and s.id not in known),
        key=lambda s: (s.level, s.name),
    )


_INT_BEGINNING_SPELLS = [
    (3, 1), (5, 1), (7, 2), (9, 2), (12, 3), (14, 3), (16, 4), (17, 4), (18, 5),
]


def beginning_spells_for_int(int_score: int) -> int:
    """OSE Advanced 'Advanced Spell Book Rules' beginning-spells table (p112)."""
    for ceiling, count in _INT_BEGINNING_SPELLS:
        if int_score <= ceiling:
            return count
    return 5  # INT 18+


def beginning_spell_count(entry: ClassEntry, cls: CharClass, int_score: int,
                          ruleset: RuleSet) -> int:
    """How many spells an arcane caster begins with.

    advanced rule: INT-table lookup.  standard: total memorizable at the
    entry's level (sum of slots; 1 for an L1 magic-user).
    """
    if ruleset.advanced_spell_books:
        return beginning_spells_for_int(int_score)
    return sum(memorizable_slots(entry, cls).values())
