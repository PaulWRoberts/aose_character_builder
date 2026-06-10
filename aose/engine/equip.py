"""Pure functions for equipping and unequipping items.

``equipped: dict[str, str]`` is the single source of truth for worn/held gear:
  * ``armor``     — body armour catalog id (unchanged)
  * ``main_hand`` — a weapon (catalog id or enchanted instance id)
  * ``off_hand``  — a shield OR an off-hand weapon (same id types)

``equip``/``unequip`` return the new ``equipped`` dict; no in-place mutation.
``validate_wield`` is the single legality gate.
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.engine.enchant import resolve_instance
from aose.engine.proficiency import base_armor_id, base_weapon_id
from aose.models import Armor, Weapon

OFF_HAND_FORBIDDEN = {"two_handed", "versatile", "slow", "brace", "charge"}


class WieldError(ValueError):
    """A weapon/shield configuration that two hands cannot hold."""


def hand_cost(item, *, gargantua_1h_2h: bool) -> int:
    """Hands consumed by an in-hand item. Body armour returns 0."""
    if isinstance(item, Armor):
        return 1 if item.is_shield else 0
    if isinstance(item, Weapon):
        if "two_handed" in item.quality_ids:
            if gargantua_1h_2h and item.melee:
                return 1
            return 2
        return 1
    return 0


def off_hand_eligible(weapon: Weapon) -> bool:
    """House rule for a 'small' off-hand weapon: <=30cn, melee, and none of the
    forbidden qualities."""
    return (
        weapon.weight_cn <= 30
        and "melee" in weapon.quality_ids
        and not (weapon.quality_ids & OFF_HAND_FORBIDDEN)
    )


def resolve_slot(value, data: GameData, enchanted):
    """Resolve a slot value to its concrete Weapon/Armor (catalog or enchanted),
    or None for an empty/stale slot."""
    if not value:
        return None
    if value in data.items:
        return data.items[value]
    for inst in enchanted:
        if inst.instance_id == value:
            return resolve_instance(inst, data)
    return None


def validate_wield(equipped: dict, data: GameData, enchanted, *,
                   two_weapon: bool, eligible: bool,
                   gargantua_1h_2h: bool) -> None:
    """Raise WieldError unless the hand slots form a legal configuration.
    Class allowances are checked separately by ``equip``; this gate is purely
    the hand budget + baseline one-weapon rule + two-weapon-fighting rules."""
    main = resolve_slot(equipped.get("main_hand"), data, enchanted)
    off = resolve_slot(equipped.get("off_hand"), data, enchanted)

    if main is not None and not isinstance(main, Weapon):
        raise WieldError("Only a weapon may be held in the main hand")

    used = (hand_cost(main, gargantua_1h_2h=gargantua_1h_2h) if main else 0)
    used += (hand_cost(off, gargantua_1h_2h=gargantua_1h_2h) if off else 0)
    if used > 2:
        raise WieldError("Both hands are full")

    if isinstance(off, Weapon):
        if not two_weapon:
            raise WieldError("Two-weapon fighting is not enabled")
        if not eligible:
            raise WieldError("This character is not eligible to fight with two weapons")
        if main is None:
            raise WieldError("Equip a main-hand weapon before an off-hand weapon")
        if not off_hand_eligible(off):
            raise WieldError(f"{off.name!r} is not a valid off-hand weapon")

def _count(seq, value) -> int:
    return sum(1 for v in seq if v == value)


def equip(item_id: str, *, inventory: list[str], equipped: dict[str, str],
          enchanted, data: GameData,
          slot: str | None = None,
          two_weapon: bool = False, eligible: bool = False,
          gargantua_1h_2h: bool = False,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> dict[str, str]:
    """Equip one item into a slot. ``item_id`` is a catalog id (must be owned in
    ``inventory``) or an enchanted instance id (must exist in ``enchanted``).
    Body armour always goes to ``armor``; shields always to ``off_hand``; weapons
    default to ``main_hand`` unless ``slot="off_hand"`` is passed. Returns the
    new ``equipped`` dict. Raises ValueError/WieldError on any illegality."""
    item = resolve_slot(item_id, data, enchanted)
    if item is None:
        raise ValueError(f"Unknown or unowned item {item_id!r}")

    is_catalog = item_id in data.items
    if is_catalog:
        owned = _count(inventory, item_id)
        if owned == 0:
            raise ValueError(f"{item.name!r} is not in inventory")
    else:
        owned = 1  # enchanted instance: unique, count doesn't apply

    new_eq = dict(equipped)

    if isinstance(item, Armor) and not item.is_shield:
        if allowed_armor != "all" and base_armor_id(item) not in allowed_armor:
            raise ValueError(f"This class cannot use {item.name!r}")
        new_eq["armor"] = item_id
        return new_eq

    if isinstance(item, Armor) and item.is_shield:
        if not allow_shields:
            raise ValueError("This class cannot use a shield")
        target = "off_hand"
    elif isinstance(item, Weapon):
        if allowed_weapons != "all" and base_weapon_id(item) not in allowed_weapons:
            raise ValueError(f"This class cannot use {item.name!r}")
        target = slot or "main_hand"
    else:
        raise ValueError(f"{item.name!r} is not equippable")

    if target not in ("main_hand", "off_hand"):
        raise ValueError(f"Invalid hand slot {target!r}")

    # Ownership: don't equip more catalog copies than owned across both hands.
    if is_catalog:
        in_other = sum(1 for s in ("main_hand", "off_hand")
                       if s != target and new_eq.get(s) == item_id)
        if in_other >= owned:
            raise ValueError(f"All {owned} copies of {item.name!r} already equipped")

    new_eq[target] = item_id
    validate_wield(new_eq, data, enchanted, two_weapon=two_weapon,
                   eligible=eligible, gargantua_1h_2h=gargantua_1h_2h)
    return new_eq


def unequip(item_id: str, *, equipped: dict[str, str]) -> dict[str, str]:
    """Clear whichever slot holds ``item_id``. Raises ValueError if not equipped."""
    new_eq = dict(equipped)
    for slot, val in list(new_eq.items()):
        if val == item_id:
            del new_eq[slot]
            return new_eq
    raise ValueError(f"{item_id!r} is not equipped")


def equipped_count(equipped: dict[str, str], item_id: str) -> int:
    """How many copies of an item are currently in hand/body slots."""
    return sum(1 for v in equipped.values() if v == item_id)
