"""Pure functions for equipping and unequipping items.

The wizard draft and the saved spec both use the same shape:
  * ``equipped: dict[str, str]`` for single-slot gear (``armor`` / ``shield``)
  * ``equipped_weapons: list[str]`` for any number of ready weapons (each id
    must still be present in ``inventory``; we only allow as many copies
    equipped as the character owns)

These helpers return ``(equipped, equipped_weapons)`` tuples — no in-place
mutation — and raise ``ValueError`` on bad input.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.engine.proficiency import base_armor_id, base_weapon_id
from aose.models import Armor, Weapon

Slot = Literal["armor", "shield"]


def _count(seq, value) -> int:
    return sum(1 for v in seq if v == value)


def can_equip(item, slot: str | None = None) -> bool:
    """Whether an item is equippable at all (weapon, armor, or shield)."""
    if isinstance(item, Weapon):
        return True
    if isinstance(item, Armor):
        return True
    return False


def equip(inventory: list[str], equipped: dict[str, str],
          equipped_weapons: list[str], item_id: str,
          data: GameData,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> tuple[dict[str, str], list[str]]:
    """Equip one copy of ``item_id`` from ``inventory``.  Returns new
    (equipped, equipped_weapons).  Raises ValueError if the item isn't owned
    or isn't equippable, or if a copy is already equipped that would push us
    past the inventory count.

    Optional allowance args enforce class restrictions:
      * ``allowed_weapons`` — set of permitted weapon ids, or ``"all"``
      * ``allowed_armor``   — set of permitted armour ids, or ``"all"``
      * ``allow_shields``   — False to forbid shield equipping

    Defaults leave all three unrestricted (backward-compatible).
    """
    if item_id not in data.items:
        raise ValueError(f"Unknown item {item_id!r}")
    item = data.items[item_id]
    owned = _count(inventory, item_id)
    if owned == 0:
        raise ValueError(f"{item.name!r} is not in inventory")

    new_eq = dict(equipped)
    new_weapons = list(equipped_weapons)

    if isinstance(item, Armor):
        if item.is_shield:
            if not allow_shields:
                raise ValueError("This class cannot use a shield")
        else:
            if allowed_armor != "all" and base_armor_id(item) not in allowed_armor:
                raise ValueError(f"This class cannot use {item.name!r}")
        slot = "shield" if item.is_shield else "armor"
        # Single-slot gear: replace whatever is currently in that slot.
        new_eq[slot] = item_id
        return new_eq, new_weapons

    if isinstance(item, Weapon):
        if allowed_weapons != "all" and base_weapon_id(item) not in allowed_weapons:
            raise ValueError(f"This class cannot use {item.name!r}")
        already_equipped = _count(equipped_weapons, item_id)
        if already_equipped >= owned:
            raise ValueError(
                f"All {owned} copies of {item.name!r} already equipped"
            )
        new_weapons.append(item_id)
        return new_eq, new_weapons

    raise ValueError(f"{item.name!r} is not equippable")


def unequip(equipped: dict[str, str], equipped_weapons: list[str],
            item_id: str,
            data: GameData) -> tuple[dict[str, str], list[str]]:
    """Remove one equipped instance of ``item_id`` from whichever slot/list
    it occupies.  Raises ValueError if the item isn't equipped anywhere."""
    new_eq = dict(equipped)
    new_weapons = list(equipped_weapons)

    # Try armor/shield slots first
    for slot, equipped_id in equipped.items():
        if equipped_id == item_id:
            del new_eq[slot]
            return new_eq, new_weapons

    # Then weapons
    if item_id in new_weapons:
        new_weapons.remove(item_id)
        return new_eq, new_weapons

    raise ValueError(f"{item_id!r} is not equipped")


def equipped_count(equipped: dict[str, str], equipped_weapons: list[str],
                   item_id: str) -> int:
    """How many copies of an item are currently equipped (across slots)."""
    n = sum(1 for v in equipped.values() if v == item_id)
    n += sum(1 for v in equipped_weapons if v == item_id)
    return n
