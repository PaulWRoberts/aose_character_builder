"""Spell engine — the cycle-free core for spell access, known/prepared sets,
and spellbook/prepared mutations.

Imports only models + the data loader (like ``engine/magic.py``); no derivation
module imports it back.  Arcane vs divine is read from the SpellList registry,
not the class.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.models import CharClass, ClassEntry, ClassLevelData, RuleSet, Spell, SpellSlot

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


# ── Mutators (return a new ClassEntry; raise SpellError on violation) ───────

def _require_spell(data: GameData, spell_id: str) -> Spell:
    spell = data.spells.get(spell_id)
    if spell is None:
        raise SpellError(f"Unknown spell {spell_id!r}")
    return spell


def learn(entry: ClassEntry, cls: CharClass, data: GameData, ruleset: RuleSet,
          spell_id: str) -> ClassEntry:
    """Add a spell to an arcane caster's spellbook.

    Enforces: arcane only; spell on a class list and at an accessible level;
    not already known; and (standard rules) the per-level spellbook cap."""
    if caster_type_of(cls, data) != "arcane":
        raise SpellError(f"{cls.id!r} is not an arcane caster; nothing to learn")
    spell = _require_spell(data, spell_id)
    if not _on_class_lists(spell, cls):
        raise SpellError(f"{spell_id!r} is not on {cls.id!r}'s spell list")
    if spell.level not in accessible_levels(entry, cls):
        raise SpellError(f"{spell_id!r} (level {spell.level}) is not castable yet")
    if spell_id in entry.spellbook:
        raise SpellError(f"{spell_id!r} is already known")
    if not ruleset.advanced_spell_books:
        cap = memorizable_slots(entry, cls).get(spell.level, 0)
        have = sum(1 for s in entry.spellbook
                   if s in data.spells and data.spells[s].level == spell.level)
        if have >= cap:
            raise SpellError(
                f"Standard spell-book rules: only {cap} level-{spell.level} "
                f"spell(s) may be known at this level"
            )
    return entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})


def forget(entry: ClassEntry, spell_id: str) -> ClassEntry:
    if spell_id not in entry.spellbook:
        raise SpellError(f"{spell_id!r} is not in the spell book")
    book = list(entry.spellbook)
    book.remove(spell_id)
    return entry.model_copy(update={"spellbook": book})


# ── Slot memorization / casting / rest (play state) ────────────────────────

def _check_index(entry: ClassEntry, index: int) -> None:
    if index < 0 or index >= len(entry.slots):
        raise SpellError(f"No slot at index {index}")


def _free_slots_at(entry: ClassEntry, cls: CharClass, level: int) -> int:
    cap = memorizable_slots(entry, cls).get(level, 0)
    used = sum(1 for s in entry.slots if s.level == level)
    return cap - used


def assign_slot(entry: ClassEntry, cls: CharClass, data: GameData, level: int,
                spell_id: str, reversed: bool = False) -> ClassEntry:
    """Memorize ``spell_id`` into a free slot at ``level``.

    Enforces: spell known (arcane spellbook / divine accessible list),
    ``spell.level == level``, a free slot exists at that level (cap from
    ``memorizable_slots``), and ``reversed`` only for a reversible spell on an
    arcane caster.  New slot starts unspent."""
    spell = _require_spell(data, spell_id)
    if spell.level != level:
        raise SpellError(f"{spell_id!r} is level {spell.level}, not {level}")
    known_ids = {s.id for s in known_spells(entry, cls, data)}
    if spell_id not in known_ids:
        raise SpellError(f"{spell_id!r} is not known and cannot be memorized")
    if _free_slots_at(entry, cls, level) <= 0:
        cap = memorizable_slots(entry, cls).get(level, 0)
        raise SpellError(f"No free level-{level} slot (cap {cap})")
    if reversed and not (caster_type_of(cls, data) == "arcane" and spell.reversible):
        raise SpellError(f"{spell_id!r} cannot be memorized reversed")
    new = SpellSlot(level=level, spell_id=spell_id, reversed=reversed, spent=False)
    return entry.model_copy(update={"slots": [*entry.slots, new]})


def _set_slot(entry: ClassEntry, index: int, **changes) -> ClassEntry:
    _check_index(entry, index)
    slots = [s.model_copy(update=changes) if i == index else s
             for i, s in enumerate(entry.slots)]
    return entry.model_copy(update={"slots": slots})


def cast_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Mark a memorized slot spent.  Raises if empty or already spent."""
    _check_index(entry, index)
    slot = entry.slots[index]
    if slot.spell_id is None:
        raise SpellError(f"Slot {index} is empty")
    if slot.spent:
        raise SpellError(f"Slot {index} is already spent")
    return _set_slot(entry, index, spent=True)


def restore_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Mark a single slot available again (undo / referee override)."""
    return _set_slot(entry, index, spent=False)


def clear_slot(entry: ClassEntry, index: int) -> ClassEntry:
    """Remove a slot row entirely (un-memorize)."""
    _check_index(entry, index)
    slots = [s for i, s in enumerate(entry.slots) if i != index]
    return entry.model_copy(update={"slots": slots})


def restore_all_slots(entry: ClassEntry) -> ClassEntry:
    """Re-memorize the same loadout: every slot becomes available."""
    slots = [s.model_copy(update={"spent": False}) for s in entry.slots]
    return entry.model_copy(update={"slots": slots})


def clear_all_slots(entry: ClassEntry) -> ClassEntry:
    """Drop the whole loadout, ready for a fresh pick."""
    return entry.model_copy(update={"slots": []})
