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

from aose.models import Armor, CharClass, CharacterSpec, Weapon

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


# ── Base weapon resolution (magic variants count as their mundane type) ──────

def base_weapon_id(weapon: Weapon) -> str:
    """The mundane weapon type a (possibly magical/variant) weapon counts as for
    proficiency.  Variant weapons declare ``base_weapon``; a plain weapon is its
    own base.  Proficiency is per weapon *type*, so a "Sword +1" is the same
    proficiency as a "Sword"."""
    return weapon.base_weapon or weapon.id


def base_armor_id(armor: Armor) -> str:
    """The mundane armour type a (possibly magical/variant) piece counts as for
    class allowances.  Variant armour declares ``base_armor``; plain armour is
    its own base, so "Chain Mail +1" is allowed wherever "Chain Mail" is."""
    return armor.base_armor or armor.id


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


# ── Class allowance resolver ────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase and strip every non-alphanumeric character so that prose like
    ``war hammer`` / ``chainmail`` / ``plate mail`` all collapse onto the same
    key as the catalog id/name (``war_hammer`` / ``chain_mail`` / ``plate_mail``)."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _resolve_entries(entries: list[str], candidates) -> "set[str] | str":
    """Resolve prose allowance entries to item ids by matching normalised ids
    and names, plus unique first-word-of-name aliases (so ``leather`` →
    ``leather_armor``).  Any entry that resolves to nothing → ``"all"``
    (fail-open)."""
    by_key: dict[str, str] = {}
    for item in candidates:
        by_key[_normalize(item.id)] = item.id
        by_key[_normalize(item.name)] = item.id
    # Unique first-word-of-name aliases (e.g. "Leather Armour" → "leather").
    first_word_counts: dict[str, int] = {}
    first_word_id: dict[str, str] = {}
    for item in candidates:
        words = item.name.split()
        if not words:
            continue
        fw = _normalize(words[0])
        if not fw:
            continue
        first_word_counts[fw] = first_word_counts.get(fw, 0) + 1
        first_word_id[fw] = item.id
    for fw, count in first_word_counts.items():
        if count == 1 and fw not in by_key:
            by_key[fw] = first_word_id[fw]
    resolved: set[str] = set()
    for entry in entries:
        match = by_key.get(_normalize(entry))
        if match is None:
            return "all"  # freeform / unrecognised → unrestricted
        resolved.add(match)
    return resolved


def _union(values: list["set[str] | str"]) -> "set[str] | str":
    out: set[str] = set()
    for v in values:
        if v == "all":
            return "all"
        out |= v
    return out


def allowed_weapon_ids(classes: list[CharClass], data) -> "set[str] | str":
    weapons = [i for i in data.items.values() if isinstance(i, Weapon)]
    per_class: list["set[str] | str"] = []
    for cls in classes:
        if cls.weapons_allowed == "all":
            per_class.append("all")
        else:
            per_class.append(_resolve_entries(list(cls.weapons_allowed), weapons))
    return _union(per_class)


def allowed_armor_ids(classes: list[CharClass], data) -> "set[str] | str":
    armors = [i for i in data.items.values() if isinstance(i, Armor) and not i.is_shield]
    per_class: list["set[str] | str"] = []
    for cls in classes:
        if cls.armor_allowed == "all":
            per_class.append("all")
        elif not cls.armor_allowed:           # empty list → nothing allowed
            per_class.append(set())
        else:
            per_class.append(_resolve_entries(list(cls.armor_allowed), armors))
    return _union(per_class)


def shields_allowed(classes: list[CharClass]) -> bool:
    return any(cls.shields_allowed for cls in classes)

