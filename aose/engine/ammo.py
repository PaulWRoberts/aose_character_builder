"""Ammunition engine — cycle-free core for ammo stacks, loading, and the
magic-ammo bonus a loaded stack confers to its launcher.

Imports only models, the loader, dice, and ``enchant`` (for compatibility +
display name).  Mutators return a new list/dict (the ``enchant``/``magic`` style).
"""
from __future__ import annotations

import uuid

from aose.data.loader import GameData
from aose.engine.enchant import is_compatible
from aose.models import Ammunition, AmmoStack, ConditionalBonus, Weapon


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


def _find(stacks: list[AmmoStack], instance_id: str) -> int:
    for i, s in enumerate(stacks):
        if s.instance_id == instance_id:
            return i
    raise UnknownAmmo(f"No ammo stack {instance_id!r}")


def _combine(stacks: list[AmmoStack], base_id: str, enchantment_id: str | None,
             count: int) -> list[AmmoStack]:
    """Add ``count`` to an existing (base_id, enchantment_id) stack, or append a
    fresh one."""
    for i, s in enumerate(stacks):
        if s.base_id == base_id and s.enchantment_id == enchantment_id:
            merged = s.model_copy(update={"count": s.count + count})
            return [*stacks[:i], merged, *stacks[i + 1:]]
    fresh = AmmoStack(instance_id=uuid.uuid4().hex, base_id=base_id,
                      enchantment_id=enchantment_id, count=count)
    return [*stacks, fresh]


def buy_ammo(stacks: list[AmmoStack], gold: int, base_id: str,
             data: GameData) -> tuple[list[AmmoStack], int]:
    """Purchase one bundle of mundane ammo: subtract cost, add ``bundle_count``."""
    base = _ammo_base(base_id, data)
    cost = int(base.cost_gp)
    if gold < cost:
        raise InsufficientGold(f"Need {cost} gp, have {gold}")
    return _combine(stacks, base_id, None, base.bundle_count), gold - cost


def add_free_ammo(stacks: list[AmmoStack], base_id: str,
                  enchantment_id: str | None, data: GameData) -> list[AmmoStack]:
    """GM grant.  Mundane (enchantment_id None) adds one bundle; magic adds 1
    unit (count is adjusted up manually).  Validates compatibility."""
    base = _ammo_base(base_id, data)
    if enchantment_id is None:
        return _combine(stacks, base_id, None, base.bundle_count)
    ench = data.enchantments.get(enchantment_id)
    if ench is None or ench.kind != "ammunition":
        raise IncompatibleAmmo(f"{enchantment_id!r} is not an ammunition enchantment")
    if not is_compatible(base, ench):
        raise IncompatibleAmmo(f"{base_id!r} is not compatible with {enchantment_id!r}")
    return _combine(stacks, base_id, enchantment_id, 1)


def adjust_count(stacks: list[AmmoStack], instance_id: str, delta: int) -> list[AmmoStack]:
    """Change a stack's count (clamped >= 0).  Count 0 removes the stack."""
    idx = _find(stacks, instance_id)
    new_count = max(0, stacks[idx].count + delta)
    if new_count == 0:
        return [*stacks[:idx], *stacks[idx + 1:]]
    updated = stacks[idx].model_copy(update={"count": new_count})
    return [*stacks[:idx], updated, *stacks[idx + 1:]]


def remove_ammo(stacks: list[AmmoStack], instance_id: str) -> list[AmmoStack]:
    idx = _find(stacks, instance_id)
    return [*stacks[:idx], *stacks[idx + 1:]]


def load(loaded: dict[str, str], weapon_key: str, instance_id: str) -> dict[str, str]:
    return {**loaded, weapon_key: instance_id}


def unload(loaded: dict[str, str], weapon_key: str) -> dict[str, str]:
    return {k: v for k, v in loaded.items() if k != weapon_key}


def loaded_stack(weapon_key: str, spec, data: GameData) -> AmmoStack | None:
    """The AmmoStack loaded into ``weapon_key``, or None if nothing valid."""
    iid = spec.loaded_ammo.get(weapon_key)
    if iid is None:
        return None
    for s in spec.ammo:
        if s.instance_id == iid and s.count > 0:
            return s
    return None


def loaded_bonus(weapon_key: str, spec, data: GameData) -> tuple[int, ConditionalBonus | None]:
    """The flat magic_bonus + conditional_bonus the loaded ammo confers."""
    stack = loaded_stack(weapon_key, spec, data)
    if stack is None or stack.enchantment_id is None:
        return 0, None
    ench = data.enchantments.get(stack.enchantment_id)
    if ench is None:
        return 0, None
    return ench.magic_bonus, ench.conditional_bonus


def is_unloaded(weapon_key: str, weapon: Weapon, spec, data: GameData) -> bool:
    """True for a launcher (accepts_ammo non-empty) with no valid loaded ammo."""
    if not weapon.accepts_ammo:
        return False
    return loaded_stack(weapon_key, spec, data) is None


def resolve_ammo(stack: AmmoStack, data: GameData) -> dict:
    """Display view: name (+ enchantment), magic_bonus, conditional_bonus."""
    base = data.items.get(stack.base_id)
    name = base.name if base else stack.base_id
    magic_bonus, conditional = 0, None
    if stack.enchantment_id:
        ench = data.enchantments.get(stack.enchantment_id)
        if ench:
            name = ench.name_template.format(base=name)
            magic_bonus, conditional = ench.magic_bonus, ench.conditional_bonus
    return {"instance_id": stack.instance_id, "name": name, "count": stack.count,
            "magic_bonus": magic_bonus, "conditional": conditional,
            "base_id": stack.base_id, "enchantment_id": stack.enchantment_id}
