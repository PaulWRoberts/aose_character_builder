"""Enchantment engine — the cycle-free core for magic-item composition.

Imports only models, the data loader, and dice (like ``magic.py``).  The
derivation modules import *from here*, never the other way round.

A magic weapon/armour is composed at runtime from a base catalog item + a
reusable ``Enchantment``.  ``resolve_weapon`` / ``resolve_armor`` return a
synthetic ``Weapon`` / ``Armor``; nothing composed is persisted.

``resolve(inst, data)`` is the single entry point: plain ItemInstance →
catalog item; enchanted ItemInstance → composed synthetic.  The old separate
list-based equip/unequip are gone (enchanted gear is now an ItemInstance in
spec.items, equipped via aose.engine.equip like any other item).
"""
from __future__ import annotations

import random
import uuid

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import (
    Armor,
    Enchantment,
    ItemInstance,
    Weapon,
)


class UnknownEnchantment(ValueError):
    pass


class IncompatibleBase(ValueError):
    pass


class NoCharges(ValueError):
    pass


_WILDCARDS = {"any_weapon", "any_armour", "any_shield", "any_ammunition"}


def _is_weapon(base) -> bool:
    return isinstance(base, Weapon)


def _is_armour(base) -> bool:
    return isinstance(base, Armor) and not base.is_shield


def _is_shield(base) -> bool:
    return isinstance(base, Armor) and base.is_shield


def _is_ammunition(base) -> bool:
    from aose.models import Ammunition
    return isinstance(base, Ammunition)


def matches(base, token: str) -> bool:
    """A base item matches ``token`` if it is the kind wildcard for the base's
    nature, equals the base id, or appears in ``base.groups``."""
    if token == "any_weapon":
        return _is_weapon(base)
    if token == "any_armour":
        return _is_armour(base)
    if token == "any_shield":
        return _is_shield(base)
    if token == "any_ammunition":
        return _is_ammunition(base)
    if token == base.id:
        return True
    return token in getattr(base, "groups", [])


def _nature_matches_kind(base, kind: str) -> bool:
    return (
        (kind == "weapon" and _is_weapon(base))
        or (kind == "armor" and _is_armour(base))
        or (kind == "shield" and _is_shield(base))
        or (kind == "ammunition" and _is_ammunition(base))
    )


def is_compatible(base, ench: Enchantment) -> bool:
    """A base is compatible when its nature matches the enchantment kind, it
    matches at least one ``include`` token, and no ``exclude`` token (exclude
    wins)."""
    if not _nature_matches_kind(base, ench.kind):
        return False
    if any(matches(base, t) for t in ench.applies_to.exclude):
        return False
    return any(matches(base, t) for t in ench.applies_to.include)


def compatible_bases(ench: Enchantment, data: GameData) -> list:
    """Every catalog base item compatible with ``ench``, sorted by name."""
    out = [item for item in data.items.values()
           if isinstance(item, (Weapon, Armor)) and is_compatible(item, ench)]
    out.sort(key=lambda i: i.name)
    return out


def resolve_weapon(base: Weapon, ench: Enchantment, instance_id: str) -> Weapon:
    """Synthetic ``Weapon`` = base combat stats + enchantment bonus."""
    return Weapon(
        id=f"ench:{instance_id}",
        name=ench.name_template.format(base=base.name),
        category=base.category,
        cost_gp=0,
        weight_cn=base.weight_cn,
        magic=True,
        item_type="weapon",
        damage=base.damage,
        qualities=[q.model_copy() for q in base.qualities],
        groups=list(base.groups),
        accepts_ammo=list(base.accepts_ammo),
        magic_bonus=ench.magic_bonus,
        conditional_bonus=ench.conditional_bonus,
        base_weapon=base.id,
    )


def resolve_armor(base: Armor, ench: Enchantment, instance_id: str) -> Armor:
    """Synthetic ``Armor`` = base defence stats + enchantment bonus."""
    return Armor(
        id=f"ench:{instance_id}",
        name=ench.name_template.format(base=base.name),
        category=base.category,
        cost_gp=0,
        weight_cn=base.weight_cn,
        magic=True,
        item_type="armor",
        ac_descending=base.ac_descending,
        ac_bonus=base.ac_bonus,
        movement_impact=base.movement_impact,
        is_shield=base.is_shield,
        groups=list(base.groups),
        magic_bonus=ench.magic_bonus,
        weight_multiplier=0.5,
        base_armor=base.id,
    )


def _kind_of_instance(inst: ItemInstance, data: GameData) -> str | None:
    ench = data.enchantments.get(inst.enchantment_id) if inst.enchantment_id else None
    return ench.kind if ench else None


def _index(items: list[ItemInstance], instance_id: str) -> int:
    for i, m in enumerate(items):
        if m.instance_id == instance_id:
            return i
    raise UnknownEnchantment(f"No enchanted instance {instance_id!r}")


def resolve_instance(inst: ItemInstance, data: GameData):
    """Resolve one instance to its synthetic Weapon/Armor, or None if its base
    or enchantment is missing from the catalog."""
    base_key = getattr(inst, "catalog_id", None) or getattr(inst, "base_id", None)
    base = data.items.get(base_key)
    ench = data.enchantments.get(inst.enchantment_id) if inst.enchantment_id else None
    if ench is None or not isinstance(base, (Weapon, Armor)):
        return None
    if ench.kind == "weapon":
        return resolve_weapon(base, ench, inst.instance_id)
    return resolve_armor(base, ench, inst.instance_id)


def resolve(inst: ItemInstance, data: GameData):
    """Resolve an ItemInstance to its effective catalog item.
    Plain (enchantment_id is None) → the base catalog item; enchanted →
    the composed synthetic Weapon/Armor (or None if base/enchantment missing)."""
    if inst.enchantment_id is None:
        return data.items.get(inst.catalog_id)
    return resolve_instance(inst, data)


def new_enchanted_instance(base_id: str, enchantment_id: str, data: GameData,
                           rng: random.Random | None = None) -> ItemInstance:
    """Create a fresh enchanted ItemInstance.  Validates the base exists, the
    enchantment exists, and the two are compatible.  Rolls ``charge_dice`` or
    seeds ``max_charges``."""
    base = data.items.get(base_id)
    if not isinstance(base, (Weapon, Armor)):
        raise ValueError(f"{base_id!r} is not a base weapon or armour")
    ench = data.enchantments.get(enchantment_id)
    if ench is None:
        raise UnknownEnchantment(f"{enchantment_id!r} is not an enchantment")
    if not is_compatible(base, ench):
        raise IncompatibleBase(f"{base_id!r} is not compatible with {enchantment_id!r}")
    charges_max: int | None = None
    if ench.charge_dice:
        charges_max = roll(ench.charge_dice, rng)
    elif ench.max_charges is not None:
        charges_max = ench.max_charges
    return ItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=base_id,
        enchantment_id=enchantment_id,
        equip=None,
        charges_max=charges_max,
        charges_remaining=charges_max,
    )


def add_free_enchanted(spec, base_id: str, enchantment_id: str, data: GameData) -> None:
    """Append a new enchanted ItemInstance to spec.items."""
    spec.items.append(new_enchanted_instance(base_id, enchantment_id, data))


def equipped_enchanted(spec, data: GameData, kind: str) -> list:
    """Resolved synthetic items for every EQUIPPED enchanted instance of the
    given ``kind`` (``weapon`` / ``armor`` / ``shield``)."""
    out = []
    for inst in spec.items:
        if inst.enchantment_id is None or inst.equip is None:
            continue
        if _kind_of_instance(inst, data) != kind:
            continue
        resolved = resolve_instance(inst, data)
        if resolved is not None:
            out.append(resolved)
    return out


def use_charge(items: list[ItemInstance], instance_id: str) -> list[ItemInstance]:
    idx = _index(items, instance_id)
    inst = items[idx]
    if inst.charges_remaining is None or inst.charges_remaining <= 0:
        raise NoCharges(f"{inst.enchantment_id!r} has no charges left")
    updated = inst.model_copy(update={"charges_remaining": inst.charges_remaining - 1})
    return [*items[:idx], updated, *items[idx + 1:]]


def reset_charges(items: list[ItemInstance], instance_id: str) -> list[ItemInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"charges_remaining": items[idx].charges_max})
    return [*items[:idx], updated, *items[idx + 1:]]


def remove(items: list[ItemInstance], instance_id: str) -> list[ItemInstance]:
    idx = _index(items, instance_id)
    return [*items[:idx], *items[idx + 1:]]


def set_note(items: list[ItemInstance], instance_id: str, note: str) -> list[ItemInstance]:
    idx = _index(items, instance_id)
    updated = items[idx].model_copy(update={"note": note})
    return [*items[:idx], updated, *items[idx + 1:]]
