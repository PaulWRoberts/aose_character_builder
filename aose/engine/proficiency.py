"""Helpers for the Weapon Proficiency optional rule."""
from __future__ import annotations

from typing import TypedDict

from aose.data.loader import GameData
from aose.models import CharClass, Weapon


# Default slot count when a class doesn't specify its own proficiency config.
# Most classes get 2 starting slots in AOSE Advanced; fighters get more and
# should declare it explicitly in their data file.
_DEFAULT_STARTING_SLOTS = 2


class ProficiencyGroup(TypedDict):
    id: str
    name: str
    weapons: list[str]


def starting_proficiency_count(cls: CharClass) -> int:
    """How many proficiency slots a freshly-created character of this class has."""
    if cls.proficiency is not None:
        return cls.proficiency.starting_slots
    return _DEFAULT_STARTING_SLOTS


def proficiency_groups(data: GameData) -> list[ProficiencyGroup]:
    """List the unique proficiency groups found across weapons in the data set,
    each with a human-readable name and the weapons it covers.  Groups and
    their weapons are sorted alphabetically for stable rendering."""
    groups: dict[str, list[str]] = {}
    for item in data.items.values():
        if isinstance(item, Weapon) and item.proficiency_group:
            groups.setdefault(item.proficiency_group, []).append(item.name)

    out: list[ProficiencyGroup] = []
    for gid in sorted(groups):
        out.append({
            "id": gid,
            "name": gid.replace("_", " ").title(),
            "weapons": sorted(groups[gid]),
        })
    return out


def is_proficient_with(weapon: Weapon, chosen: list[str]) -> bool:
    """True if the character's chosen proficiencies cover this weapon's group."""
    return weapon.proficiency_group is not None and weapon.proficiency_group in chosen
