"""Energy drain — the permanent, GM-applied loss of experience levels.

A sheet-manager-only mutation (no wizard, no RuleSet flag). Removes levels
LIFO: the most recently gained level across all of a character's classes goes
first. Each lost level drops the class's last Hit Die roll and trims its
now-inaccessible spells; saves / THAC0 / attacks fall out of the reduced level
automatically.

Multi-class LIFO is deterministic with no stored timeline: XP is split evenly
across classes and each class has its own XP table, so the class that levelled
most recently is the one whose current-level XP threshold, converted back to the
shared "global" XP it represents (threshold / prime-req multiplier), is highest.
Level 1 needs 0 XP in every OSE table, so a level-1 class never wins that
comparison while another class is above 1 — classes bottom out together at
creation. When every class is at level 1 and a level must still be removed, the
drain is fatal.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.engine.hp import max_hp
from aose.engine.leveling import _prime_req_multiplier
from aose.engine.spells import accessible_levels, caster_type_of, memorizable_slots
from aose.models import CharacterSpec, ClassEntry, RuleSet

XpMode = Literal["midpoint", "new_min"]


def _xp_required(cls, level: int) -> int:
    """XP threshold for ``level`` from the class table (0 if no such row)."""
    row = cls.progression.get(level)
    return row.xp_required if row is not None else 0


def _most_recently_leveled(spec: CharacterSpec, data: GameData) -> ClassEntry | None:
    """The class entry whose current level was attained latest in shared-XP
    terms (``xp_required(level) / prime_req_multiplier``), among classes above
    level 1. ``None`` when every class is at level 1."""
    candidates = [e for e in spec.classes if e.level > 1]
    if not candidates:
        return None

    def global_xp(entry: ClassEntry) -> float:
        cls = data.classes[entry.class_id]
        return _xp_required(cls, entry.level) / _prime_req_multiplier(cls, spec.abilities)

    return max(candidates, key=global_xp)


def _trim_to_accessible(entry: ClassEntry, data: GameData, ruleset: RuleSet) -> None:
    """Drop spells the class can no longer use at its reduced level: prepared
    slots above the accessible levels or beyond the per-level cap, and arcane
    spellbook entries above the accessible levels (and beyond the per-level cap
    under standard spell-book rules). Mutates ``entry`` in place. No-op for
    non-casters and divine known-spells (which are derived, not stored)."""
    cls = data.classes.get(entry.class_id)
    if cls is None or caster_type_of(cls, data) is None:
        return
    levels = accessible_levels(entry, cls)
    caps = memorizable_slots(entry, cls)

    kept = []
    used: dict[int, int] = {}
    for slot in entry.slots:
        if slot.level not in levels:
            continue
        if used.get(slot.level, 0) >= caps.get(slot.level, 0):
            continue
        used[slot.level] = used.get(slot.level, 0) + 1
        kept.append(slot)
    entry.slots = kept

    if caster_type_of(cls, data) == "arcane":
        book = []
        bused: dict[int, int] = {}
        for spell_id in entry.spellbook:
            spell = data.spells.get(spell_id)
            if spell is None or spell.level not in levels:
                continue
            if not ruleset.advanced_spell_books:
                if bused.get(spell.level, 0) >= caps.get(spell.level, 0):
                    continue
                bused[spell.level] = bused.get(spell.level, 0) + 1
            book.append(spell_id)
        entry.spellbook = book


def _kill(spec: CharacterSpec, data: GameData) -> None:
    """Fatal drain: reset every class to level 1 / one Hit Die / 0 XP, trim
    spells, then set current HP to 0."""
    for entry in spec.classes:
        entry.level = 1
        entry.hp_rolls = entry.hp_rolls[:1]
        entry.xp = 0
        _trim_to_accessible(entry, data, spec.ruleset)
    spec.damage_taken = max_hp(spec, data)


def energy_drain(spec: CharacterSpec, data: GameData, levels: int,
                 xp_mode: XpMode) -> None:
    """Remove ``levels`` experience levels LIFO, mutating ``spec`` in place.

    ``levels`` must be >= 1. ``xp_mode`` sets each drained class's XP afterward:
    ``midpoint`` = halfway between its former and new level thresholds (only
    valid for a single-level drain); ``new_min`` = the new level's threshold. If
    the drain exhausts the character (a level must be removed while every class
    is at level 1), the character dies."""
    if levels < 1:
        raise ValueError("levels must be at least 1")
    if xp_mode not in ("midpoint", "new_min"):
        raise ValueError(f"unknown xp_mode {xp_mode!r}")
    if xp_mode == "midpoint" and levels != 1:
        raise ValueError("midpoint XP is only valid for a single-level drain")

    former: dict[str, int] = {}  # class_id -> level before this drain
    for _ in range(levels):
        target = _most_recently_leveled(spec, data)
        if target is None:
            _kill(spec, data)
            return
        former.setdefault(target.class_id, target.level)
        removed_level = target.level  # the level being stripped
        target.level -= 1
        # Levels above name level never rolled a Hit Die, so there is nothing to
        # pop; only remove a stored roll when the removed level had one.
        if removed_level <= data.classes[target.class_id].name_level and target.hp_rolls:
            target.hp_rolls.pop()
        _trim_to_accessible(target, data, spec.ruleset)

    for class_id, former_level in former.items():
        entry = next(e for e in spec.classes if e.class_id == class_id)
        cls = data.classes[entry.class_id]
        new_req = _xp_required(cls, entry.level)
        if xp_mode == "midpoint":
            entry.xp = (new_req + _xp_required(cls, former_level)) // 2
        else:
            entry.xp = new_req
