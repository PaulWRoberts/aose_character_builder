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
    their weapons are sorted alphabetically for stable rendering.

    NOTE: proficiency_group was removed from the Weapon model in Task 3 of the
    weapon-proficiency fix plan.  This function is a stub that returns an empty
    list until Task 4 re-implements it using weapon qualities + categories.
    """
    return []


def is_proficient_with(weapon: Weapon, chosen: list[str]) -> bool:
    """True if the character's chosen proficiencies cover this weapon's group.

    NOTE: stub pending Task 4/8 re-implementation using qualities/categories.
    """
    return False
