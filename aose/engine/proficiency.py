"""Weapon Proficiency optional rule — per-weapon proficiencies.

The character's *combat category* (martial / semi_martial / non_martial) is
DERIVED from the rate at which its THAC0 improves, so class data stays the
single source of truth:

* martial      — THAC0 improves every 3 levels (first drop at L4) → 4 slots, -2
* semi_martial — every 4 levels (first drop at L5)               → 3 slots, -3
* non_martial  — every 5 levels (first drop at L6)               → 1 slot,  -5

One extra proficiency slot is gained each time THAC0 improves.
"""
from __future__ import annotations

from typing import Literal

from aose.models import CharClass, CharacterSpec

Category = Literal["martial", "semi_martial", "non_martial"]

_BASE_SLOTS: dict[Category, int] = {"martial": 4, "semi_martial": 3, "non_martial": 1}
_PENALTY: dict[Category, int] = {"martial": -2, "semi_martial": -3, "non_martial": -5}
# Most-martial-first ordering for multi-class resolution.
_MARTIALNESS: dict[Category, int] = {"martial": 0, "semi_martial": 1, "non_martial": 2}


def combat_category(cls: CharClass) -> Category:
    """Derive the proficiency category from the THAC0 progression's improvement
    rate.  Falls back to ``non_martial`` (safest: fewest slots) if the table
    never improves."""
    levels = sorted(cls.progression)
    if not levels:
        return "non_martial"
    base = cls.progression[levels[0]].thac0
    for lvl in levels[1:]:
        if cls.progression[lvl].thac0 < base:
            period = lvl - 1
            if period <= 3:
                return "martial"
            if period == 4:
                return "semi_martial"
            return "non_martial"
    return "non_martial"


def base_slot_count(category: Category) -> int:
    return _BASE_SLOTS[category]


def nonproficiency_penalty(category: Category) -> int:
    return _PENALTY[category]


def improvements_through_level(cls: CharClass, level: int) -> int:
    """Count THAC0 improvements (drops) at levels <= ``level``."""
    levels = sorted(cls.progression)
    if not levels:
        return 0
    count = 0
    prev = cls.progression[levels[0]].thac0
    for lvl in levels[1:]:
        if lvl > level:
            break
        cur = cls.progression[lvl].thac0
        if cur < prev:
            count += 1
        prev = cur
    return count


def proficiency_slots(cls: CharClass, level: int) -> int:
    """Total proficiency slots for a single class at ``level`` = base + gained."""
    return base_slot_count(combat_category(cls)) + improvements_through_level(cls, level)


# ── Per-character accounting ────────────────────────────────────────────────

def is_proficient(weapon_id: str, spec: CharacterSpec) -> bool:
    return weapon_id in spec.weapon_proficiencies


def is_specialised(weapon_id: str, spec: CharacterSpec) -> bool:
    return weapon_id in spec.weapon_specialisations


def slots_spent(spec: CharacterSpec) -> int:
    """Each proficiency costs 1 slot; each specialisation costs 1 extra."""
    return len(spec.weapon_proficiencies) + len(spec.weapon_specialisations)


# ── Multi-class resolution (book is silent; most-martial wins) ──────────────

def category_for_classes(classes: list[CharClass]) -> Category:
    """The most martial category among the classes (smallest penalty)."""
    return min((combat_category(c) for c in classes),
               key=lambda cat: _MARTIALNESS[cat], default="non_martial")


def penalty_for_classes(classes: list[CharClass]) -> int:
    return nonproficiency_penalty(category_for_classes(classes))


def specialisation_allowed(classes: list[CharClass]) -> bool:
    """Specialisation is offered when any class is martial."""
    return any(combat_category(c) == "martial" for c in classes)


def total_proficiency_slots(pairs: list[tuple[CharClass, int]]) -> int:
    """Total slots for a (possibly multi-class) character: the max over classes
    of that class's slot count at its level."""
    return max((proficiency_slots(c, lvl) for c, lvl in pairs), default=0)
