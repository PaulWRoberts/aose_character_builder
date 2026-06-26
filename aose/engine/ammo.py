"""Ammunition engine — cycle-free core for ammo stacks, loading, and the
magic-ammo bonus a loaded stack confers to its launcher.

Ammo is now a flat ItemInstance in spec.items (catalog_id = the ammo base id,
enchantment_id optional, count >= 1).  The loaded-state lives on the weapon's
ItemInstance: ``loaded_ammo_id`` is the instance_id of the loaded ammo item.

buy/add/adjust helpers that operated on the old list[AmmoStack] are removed;
shop.py handles those in the unified items bucket (Task 17).
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.engine.enchant import is_compatible
from aose.models import Ammunition, ConditionalBonus, Weapon
from aose.models.storage import StorageLocation


class UnknownAmmo(ValueError):
    pass


class IncompatibleAmmo(ValueError):
    pass


class InsufficientGold(ValueError):
    pass


def accepts(weapon: Weapon, ammo_base: Ammunition) -> bool:
    """True when the launcher fires this ammo (a group/id token overlaps)."""
    tokens = {ammo_base.id, *ammo_base.groups}
    return any(t in weapon.accepts_ammo for t in tokens)


def _ammo_base(base_id: str, data: GameData) -> Ammunition:
    base = data.items.get(base_id)
    if not isinstance(base, Ammunition):
        raise UnknownAmmo(f"{base_id!r} is not ammunition")
    return base


def loaded_stack(weapon_inst, spec, data: GameData):
    """The ammo ItemInstance loaded into the weapon instance, or None."""
    if weapon_inst is None:
        return None
    ammo_id = getattr(weapon_inst, "loaded_ammo_id", None)
    if ammo_id is None:
        return None
    return next((i for i in spec.items if i.instance_id == ammo_id and i.count > 0), None)


def loaded_bonus(weapon_inst, spec, data: GameData) -> tuple[int, ConditionalBonus | None]:
    """The flat magic_bonus + conditional_bonus the loaded ammo confers."""
    stack = loaded_stack(weapon_inst, spec, data)
    if stack is None or stack.enchantment_id is None:
        return 0, None
    ench = data.enchantments.get(stack.enchantment_id)
    if ench is None:
        return 0, None
    return ench.magic_bonus, ench.conditional_bonus


def is_unloaded(weapon_inst, weapon: Weapon, spec, data: GameData) -> bool:
    """True for a launcher (accepts_ammo non-empty) with no valid loaded ammo."""
    if not weapon.accepts_ammo:
        return False
    return loaded_stack(weapon_inst, spec, data) is None


def resolve_ammo(inst, data: GameData) -> dict:
    """Display view from an ammo ItemInstance: name (+ enchantment), magic_bonus,
    conditional_bonus.  inst.catalog_id is the base ammo id."""
    base = data.items.get(inst.catalog_id)
    name = base.name if base else inst.catalog_id
    magic_bonus, conditional = 0, None
    if inst.enchantment_id:
        ench = data.enchantments.get(inst.enchantment_id)
        if ench:
            name = ench.name_template.format(base=name)
            magic_bonus, conditional = ench.magic_bonus, ench.conditional_bonus
    return {"instance_id": inst.instance_id, "name": name, "count": inst.count,
            "magic_bonus": magic_bonus, "conditional": conditional,
            "base_id": inst.catalog_id, "enchantment_id": inst.enchantment_id}
