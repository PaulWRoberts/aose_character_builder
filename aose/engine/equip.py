"""Pure functions for equipping and unequipping items.

Equip state is per-instance: each ``ItemInstance`` carries an ``equip`` slot
field (``"armor" | "main_hand" | "off_hand" | None``).  ``equip()`` and
``unequip()`` mutate that field in place; ``validate_wield`` reads the live
slot occupants from the spec's items list.

``resolve_slot`` and the old dict-based signatures are kept temporarily for
callers that have not yet been migrated (they will be removed in Task 23).
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
    """<=30cn melee weapon with none of the forbidden qualities."""
    return (
        weapon.weight_cn <= 30
        and "melee" in weapon.quality_ids
        and not (weapon.quality_ids & OFF_HAND_FORBIDDEN)
    )


def resolve_slot(value, data: GameData, enchanted):
    """Resolve a slot value to its concrete Weapon/Armor (catalog or enchanted),
    or None for an empty/stale slot. Kept for unmigrated callers."""
    if not value:
        return None
    if value in data.items:
        return data.items[value]
    for inst in enchanted:
        if inst.instance_id == value:
            return resolve_instance(inst, data)
    return None


def is_equippable(item) -> bool:
    return isinstance(item, (Armor, Weapon))


def is_stackable(item) -> bool:
    return item is not None and not is_equippable(item)


# ---------------------------------------------------------------------------
# Instance-based accessors
# ---------------------------------------------------------------------------

def _find_equippable(spec, instance_id: str):
    """The ItemInstance with this id in spec.items, or None."""
    return next((i for i in spec.items if i.instance_id == instance_id), None)


def _resolve_equippable(inst, data: GameData):
    """Resolve an ItemInstance to its Weapon/Armor.
    Plain → catalog item; enchanted → compose via resolve_instance."""
    if inst.enchantment_id is None:
        return data.items.get(inst.catalog_id)
    return resolve_instance(inst, data)


def equipped_instance(spec, slot: str):
    """The ItemInstance occupying slot, or None."""
    return next((i for i in spec.items if i.equip == slot), None)


def equipped_ref(spec, slot: str) -> str | None:
    """The catalog_id of the instance equipped in slot, or None."""
    inst = equipped_instance(spec, slot)
    return inst.catalog_id if inst is not None else None


def slot_item(spec, slot: str, data: GameData):
    """Resolved Weapon/Armor in slot, or None."""
    inst = equipped_instance(spec, slot)
    return _resolve_equippable(inst, data) if inst is not None else None


def _clear_slot(spec, slot: str) -> None:
    occ = equipped_instance(spec, slot)
    if occ is not None:
        occ.equip = None


def validate_wield(spec, data: GameData, *, two_weapon: bool, eligible: bool,
                   gargantua_1h_2h: bool) -> None:
    """Raise WieldError unless the hand slots form a legal configuration."""
    main = slot_item(spec, "main_hand", data)
    off = slot_item(spec, "off_hand", data)
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


def equip(spec, instance_id: str, *, data: GameData, slot: str | None = None,
          two_weapon: bool = False, eligible: bool = False,
          gargantua_1h_2h: bool = False,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> None:
    """Equip the instance instance_id into its slot. Mutates instance.equip.
    Raises ValueError/WieldError on any illegality."""
    inst = _find_equippable(spec, instance_id)
    if inst is None:
        raise ValueError(f"Unknown or unowned item {instance_id!r}")
    if inst.location.kind != "carried":
        raise ValueError("Only carried items can be equipped")
    item = _resolve_equippable(inst, data)
    if item is None:
        raise ValueError(f"{instance_id!r} cannot be resolved to an item")

    if isinstance(item, Armor) and not item.is_shield:
        if allowed_armor != "all" and base_armor_id(item) not in allowed_armor:
            raise ValueError(f"This class cannot use {item.name!r}")
        _clear_slot(spec, "armor")
        inst.equip = "armor"
        return

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

    _clear_slot(spec, target)
    inst.equip = target
    try:
        validate_wield(spec, data, two_weapon=two_weapon, eligible=eligible,
                       gargantua_1h_2h=gargantua_1h_2h)
    except WieldError:
        inst.equip = None
        raise


def unequip(spec, instance_id: str) -> None:
    """Clear the instance's equip slot. Raises ValueError if not equipped."""
    inst = _find_equippable(spec, instance_id)
    if inst is None or inst.equip is None:
        raise ValueError(f"{instance_id!r} is not equipped")
    inst.equip = None
