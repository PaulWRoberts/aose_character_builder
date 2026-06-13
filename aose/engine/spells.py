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

CasterType = Literal["arcane", "divine", "mental"]

# CC5 Cantrips: level-0 arcane spells. Demoted Read Magic ids (hidden when the
# Read Magic Cantrip rule is on) and the level-0 replacement id.
DEMOTED_READ_MAGIC_IDS = {"magic_user_read_magic", "illusionist_read_magic"}
READ_MAGIC_CANTRIP_ID = "read_magic_cantrip"


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


def accessible_levels(entry: ClassEntry, cls: CharClass,
                      data: GameData | None = None,
                      ruleset: "RuleSet | None" = None) -> set[int]:
    """Spell levels the class can cast at the entry's level (has >=1 slot). With
    ``data``+``ruleset`` and the Cantrips rule on, includes level 0 for dedicated
    arcane casters."""
    row = _level_row(entry, cls)
    levels = set() if (row is None or not row.spell_slots) else {
        lvl for lvl, n in row.spell_slots.items() if n > 0
    }
    if _cantrip_cap(entry, cls, data, ruleset) > 0:
        levels.add(0)
    return levels


def memorizable_slots(entry: ClassEntry, cls: CharClass,
                      data: GameData | None = None,
                      ruleset: "RuleSet | None" = None) -> dict[int, int]:
    """spell-level -> slot count at the entry's level. With ``data``+``ruleset``
    and the Cantrips rule on, includes ``{0: cantrip_count(level)}`` for a
    dedicated arcane caster (the level-0 memorise cap)."""
    row = _level_row(entry, cls)
    slots = {} if (row is None or not row.spell_slots) else dict(row.spell_slots)
    cap = _cantrip_cap(entry, cls, data, ruleset)
    if cap > 0:
        slots[0] = cap
    return slots


def powers_known_cap(entry: ClassEntry, cls: CharClass) -> int:
    """Mental caster: number of powers known at the entry's level (table column)."""
    row = _level_row(entry, cls)
    return (row.powers_known or 0) if row is not None else 0


def cantrip_count(level: int) -> int:
    """CC5 cantrips known/memorisable by character level: 2 (1-2), 3 (3-4), 4 (5+)."""
    if level <= 2:
        return 2
    if level <= 4:
        return 3
    return 4


def is_dedicated_arcane(cls: CharClass, data: GameData) -> bool:
    """A 'dedicated arcane spell caster' (CC5): arcane caster type AND the class
    grants a 1st-level spell slot at character level 1."""
    if caster_type_of(cls, data) != "arcane":
        return False
    row = cls.progression.get(1)
    return bool(row and row.spell_slots and row.spell_slots.get(1, 0) > 0)


def _cantrip_cap(entry: ClassEntry, cls: CharClass,
                 data: GameData | None, ruleset: "RuleSet | None") -> int:
    """Number of cantrips (level-0 spells) this caster may know/memorise, or 0
    when the rule is off, args are missing, or the class is not dedicated arcane."""
    if data is None or ruleset is None or not getattr(ruleset, "cantrips", False):
        return 0
    if not is_dedicated_arcane(cls, data):
        return 0
    return cantrip_count(entry.level)


def beginning_cantrip_count(entry: ClassEntry, cls: CharClass,
                            data: GameData, ruleset: "RuleSet") -> int:
    """Cantrips a dedicated arcane caster begins with (= the level cap), else 0."""
    return _cantrip_cap(entry, cls, data, ruleset)


def _on_class_lists(spell: Spell, cls: CharClass) -> bool:
    return bool(set(spell.spell_lists) & set(cls.spell_lists))


def _read_magic_demoted(cls: CharClass, data: GameData | None,
                        ruleset: "RuleSet | None") -> bool:
    """True when Read Magic Cantrip applies to this caster: both rules on and a
    dedicated arcane caster."""
    if data is None or ruleset is None:
        return False
    if not (getattr(ruleset, "cantrips", False)
            and getattr(ruleset, "read_magic_cantrip", False)):
        return False
    return is_dedicated_arcane(cls, data)


def known_spells(entry: ClassEntry, cls: CharClass, data: GameData,
                 ruleset: "RuleSet | None" = None) -> list[Spell]:
    """Spells the character knows.

    arcane: the resolved spellbook (in stored order); with Read Magic Cantrip on,
    the L1 read magic is hidden and the level-0 read-magic cantrip is auto-known
    (beyond the cantrip cap).
    divine: every spell on the class's lists at an accessible level (by level,name).
    """
    ctype = caster_type_of(cls, data)
    if ctype in ("arcane", "mental"):
        out = [data.spells[s] for s in entry.spellbook if s in data.spells]
        if ctype == "arcane" and _read_magic_demoted(cls, data, ruleset):
            out = [s for s in out if s.id not in DEMOTED_READ_MAGIC_IDS]
            rm = data.spells.get(READ_MAGIC_CANTRIP_ID)
            if rm is not None and rm.id not in entry.spellbook and _on_class_lists(rm, cls):
                out.append(rm)
        return out
    if ctype == "divine":
        levels = accessible_levels(entry, cls)
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.level in levels),
            key=lambda s: (s.level, s.name),
        )
    return []


def learnable_spells(entry: ClassEntry, cls: CharClass, data: GameData,
                     ruleset: "RuleSet | None" = None) -> list[Spell]:
    """Arcane: accessible-level spells on the class's lists not yet known (with the
    Cantrips rule, level-0 cantrips are accessible; demoted/auto-known read magic
    is excluded). Mental: every on-list power not yet known (no level filter)."""
    ctype = caster_type_of(cls, data)
    known = set(entry.spellbook)
    if ctype == "mental":
        return sorted(
            (s for s in data.spells.values()
             if _on_class_lists(s, cls) and s.id not in known),
            key=lambda s: (s.level, s.name),
        )
    if ctype != "arcane":
        return []
    levels = accessible_levels(entry, cls, data, ruleset)
    hide: set[str] = set()
    if _read_magic_demoted(cls, data, ruleset):
        hide = DEMOTED_READ_MAGIC_IDS | {READ_MAGIC_CANTRIP_ID}
    return sorted(
        (s for s in data.spells.values()
         if _on_class_lists(s, cls) and s.level in levels
         and s.id not in known and s.id not in hide),
        key=lambda s: (s.level, s.name),
    )


# (INT ceiling, beginning spells, copy chance %) — OSE Advanced Spell Book table.
_INT_SPELL_TABLE = [
    (3, 1, 20), (5, 1, 30), (7, 2, 35), (9, 2, 40), (12, 3, 50),
    (14, 3, 70), (16, 4, 75), (17, 4, 85), (18, 5, 90),
]


def beginning_spells_for_int(int_score: int) -> int:
    """OSE Advanced 'Advanced Spell Book Rules' beginning-spells table (p112)."""
    for ceiling, count, _chance in _INT_SPELL_TABLE:
        if int_score <= ceiling:
            return count
    return 5  # INT 18+


def copy_chance_for_int(int_score: int) -> int:
    """OSE Advanced 'Chance of Copying' percentage (p112) for the given INT."""
    for ceiling, _count, chance in _INT_SPELL_TABLE:
        if int_score <= ceiling:
            return chance
    return 90  # INT 18+


def beginning_spell_count(entry: ClassEntry, cls: CharClass, int_score: int,
                          ruleset: RuleSet) -> int:
    """How many spells/powers a caster begins with.

    mental: powers-known cap at the entry's level (reads the progression column).
    advanced arcane rule: INT-table lookup.
    standard arcane: total memorizable at the entry's level (sum of slots).
    """
    row = _level_row(entry, cls)
    if row is not None and row.powers_known is not None:
        return powers_known_cap(entry, cls)
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
    """Add a spell/power to a caster's known set.

    mental: power on the class list, not already known, under the powers-known cap.
    arcane: spell on a class list and at an accessible level; not already known;
    and (standard rules) the per-level spellbook cap."""
    ctype = caster_type_of(cls, data)
    if ctype == "mental":
        spell = _require_spell(data, spell_id)
        if not _on_class_lists(spell, cls):
            raise SpellError(f"{spell_id!r} is not a {cls.id!r} mental power")
        if spell_id in entry.spellbook:
            raise SpellError(f"{spell_id!r} is already known")
        cap = powers_known_cap(entry, cls)
        if len(entry.spellbook) >= cap:
            raise SpellError(
                f"Only {cap} mental power(s) may be known at this level"
            )
        return entry.model_copy(update={"spellbook": [*entry.spellbook, spell_id]})
    if ctype != "arcane":
        raise SpellError(f"{cls.id!r} is not an arcane caster; nothing to learn")
    if ruleset.advanced_spell_books:
        raise SpellError(
            "under advanced rules, spells must be copied from a source "
            "(use a spell book or scroll), not learned freely"
        )
    spell = _require_spell(data, spell_id)
    if not _on_class_lists(spell, cls):
        raise SpellError(f"{spell_id!r} is not on {cls.id!r}'s spell list")
    if spell.level not in accessible_levels(entry, cls, data, ruleset):
        raise SpellError(f"{spell_id!r} (level {spell.level}) is not castable yet")
    if spell_id in entry.spellbook:
        raise SpellError(f"{spell_id!r} is already known")
    if not ruleset.advanced_spell_books:
        cap = memorizable_slots(entry, cls, data, ruleset).get(spell.level, 0)
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


def _free_slots_at(entry: ClassEntry, cls: CharClass, level: int,
                   data: GameData | None = None,
                   ruleset: "RuleSet | None" = None) -> int:
    cap = memorizable_slots(entry, cls, data, ruleset).get(level, 0)
    used = sum(1 for s in entry.slots if s.level == level)
    return cap - used


def assign_slot(entry: ClassEntry, cls: CharClass, data: GameData, level: int,
                spell_id: str, reversed: bool = False,
                ruleset: "RuleSet | None" = None) -> ClassEntry:
    """Memorize ``spell_id`` into a free slot at ``level`` (level 0 = a cantrip
    when the Cantrips rule is on)."""
    spell = _require_spell(data, spell_id)
    if spell.level != level:
        raise SpellError(f"{spell_id!r} is level {spell.level}, not {level}")
    known_ids = {s.id for s in known_spells(entry, cls, data, ruleset)}
    if spell_id not in known_ids:
        raise SpellError(f"{spell_id!r} is not known and cannot be memorized")
    if _free_slots_at(entry, cls, level, data, ruleset) <= 0:
        cap = memorizable_slots(entry, cls, data, ruleset).get(level, 0)
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


# ── Mental-powers daily-use pool (play state) ──────────────────────────────

def power_pool(entry: ClassEntry) -> int:
    """Total mental-power activations available per day: 2 x level."""
    return 2 * entry.level


def spend_power(entry: ClassEntry) -> ClassEntry:
    """Spend one daily activation.  Raises if none remain."""
    if entry.powers_used >= power_pool(entry):
        raise SpellError("No mental-power uses remaining today")
    return entry.model_copy(update={"powers_used": entry.powers_used + 1})


def restore_power(entry: ClassEntry) -> ClassEntry:
    """Un-spend one activation (undo / referee override).  Raises at zero."""
    if entry.powers_used <= 0:
        raise SpellError("No spent mental-power uses to restore")
    return entry.model_copy(update={"powers_used": entry.powers_used - 1})


def reset_powers(entry: ClassEntry) -> ClassEntry:
    """Refresh the whole daily pool (e.g. on rest).  No-op for non-mental
    entries, whose ``powers_used`` is always 0."""
    return entry.model_copy(update={"powers_used": 0})
