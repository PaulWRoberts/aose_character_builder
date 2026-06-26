"""Magic-item engine — the cycle-free core.

Imports only models, the data loader, and dice.  The derivation modules
(``armor_class``, ``saves``, ``attack_bonus``, ``attacks``, ``encumbrance``)
import *from here*, never the other way round.

``apply_modifiers`` is literal: ``set`` (last wins) → ``add`` (summed) →
``set_min`` (``max``) → ``set_max`` (``min``).  Callers for lower-is-better
targets (``ac``, ``save:*``) negate ``add`` into the descending/target
direction themselves.
"""
from __future__ import annotations

import random
import uuid

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import Ability, CharacterSpec, MagicItem, MagicItemInstance, Modifier, RolledModifier


class UnknownMagicItem(ValueError):
    pass


class NotEquippable(ValueError):
    pass


class NoCharges(ValueError):
    pass


def apply_modifiers(base: int, mods: list[Modifier], target: str) -> int:
    """Literal op semantics for one target.  See module docstring.

    NOTE: this is only used directly for ``ability:*`` (literal add = higher
    score = improvement) and ``thac0`` (realistic modifier is ``set_max``).  A
    ``thac0 add`` would literally *raise* THAC0; no seed data uses it.
    """
    relevant = [m for m in mods if m.target == target]
    result = base
    sets = [m.value for m in relevant if m.op == "set"]
    if sets:
        result = sets[-1]
    result += sum(m.value for m in relevant if m.op == "add")
    for m in relevant:
        if m.op == "set_min":
            result = max(result, m.value)
    for m in relevant:
        if m.op == "set_max":
            result = min(result, m.value)
    return result


def active_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Catalog modifiers + extra_modifiers from every EQUIPPED magic item, plus
    enchantment modifiers + extra_modifiers from every EQUIPPED enchanted
    instance.  ``magic_bonus``/``conditional_bonus`` are NOT modifiers — they
    are consumed directly by attacks/AC."""
    out: list[Modifier] = []
    for inst in spec.magic_items:
        if not inst.equipped:
            continue
        catalog = data.items.get(inst.catalog_id)
        if isinstance(catalog, MagicItem):
            out.extend(catalog.modifiers)
        out.extend(inst.extra_modifiers)
    for inst in spec.items:
        if inst.enchantment_id is None or inst.equip is None:
            continue
        ench = data.enchantments.get(inst.enchantment_id)
        if ench is not None:
            out.extend(ench.modifiers)
        out.extend(inst.extra_modifiers)
    return out


def effective_abilities(spec: CharacterSpec, data: GameData) -> dict[Ability, int]:
    """``spec.abilities`` with magic ``ability:*`` modifiers and temporary
    per-ability modifiers applied, then clamped to [3, 18].

    Order per ability: base -> magic modifiers (unclamped, as authored in
    seed data) -> + temp delta -> clamp(3, 18).  Clamping applies to every
    ability so an effective score can never sit outside the legal range.
    """
    mods = active_modifiers(spec, data)
    temp = spec.temp_ability_modifiers
    scores: dict[Ability, int] = {}
    for ab in Ability:
        base = spec.abilities[ab]
        target = f"ability:{ab.value}"
        val = apply_modifiers(base, mods, target) if any(m.target == target for m in mods) else base
        val += temp.get(ab, 0)
        scores[ab] = max(3, min(18, val))
    return scores


def set_temp_ability_modifier(temp: dict[Ability, int], ability: Ability,
                              value: int) -> dict[Ability, int]:
    """Return a new temp-modifier dict with ``ability`` set to ``value``.

    A single modifier per ability (replaces any prior).  ``value == 0`` removes
    the key so only meaningful modifiers are stored.  Does not mutate ``temp``.
    """
    updated = {k: v for k, v in temp.items() if k != ability}
    if value != 0:
        updated[ability] = value
    return updated


def carry_capacity_bonus(spec: CharacterSpec, data: GameData) -> int:
    """Effective bonus carrying capacity in cn from active modifiers.

    ``add`` accumulates; a literal ``set`` (rare) overrides the running total.
    """
    return apply_modifiers(0, active_modifiers(spec, data), "carry_capacity")


def needs_instance(item) -> bool:
    """Whether a catalog item must be tracked as a MagicItemInstance (because
    it carries mutable per-instance state: equippable or charged)."""
    return isinstance(item, MagicItem) and (
        item.equippable or item.max_charges is not None
        or item.charge_dice is not None or bool(item.rolled_modifiers)
    )


REMOVE_MODES = ("drop", "sell", "refund")


def _index(magic_items: list[MagicItemInstance], instance_id: str) -> int:
    for i, m in enumerate(magic_items):
        if m.instance_id == instance_id:
            return i
    raise UnknownMagicItem(f"No magic item instance {instance_id!r}")


def new_magic_instance(catalog_id: str, data: GameData,
                       rng: random.Random | None = None) -> MagicItemInstance:
    """Create a fresh MagicItemInstance.  Validates the catalog is a MagicItem.
    Rolls ``charge_dice`` (via engine.dice) or uses ``max_charges`` to seed
    ``charges_max == charges_remaining``; ``uuid4`` hex id."""
    item = data.items.get(catalog_id)
    if not isinstance(item, MagicItem):
        raise UnknownMagicItem(f"{catalog_id!r} is not a magic item")
    charges_max: int | None = None
    if item.charge_dice:
        charges_max = roll(item.charge_dice, rng)
    elif item.max_charges is not None:
        charges_max = item.max_charges
    extra: list[Modifier] = [
        Modifier(target=rm.target, op=rm.op, value=roll(rm.dice, rng))
        for rm in item.rolled_modifiers
    ]
    return MagicItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        equipped=False,
        charges_max=charges_max,
        charges_remaining=charges_max,
        extra_modifiers=extra,
    )


def add_free_magic_item(magic_items: list[MagicItemInstance], catalog_id: str,
                        data: GameData) -> list[MagicItemInstance]:
    return [*magic_items, new_magic_instance(catalog_id, data)]


def equip_magic(magic_items: list[MagicItemInstance], instance_id: str,
                data: GameData) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    catalog = data.items.get(magic_items[idx].catalog_id)
    if not (isinstance(catalog, MagicItem) and catalog.equippable):
        raise NotEquippable(f"{magic_items[idx].catalog_id!r} is not equippable")
    updated = magic_items[idx].model_copy(update={"equipped": True})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def unequip_magic(magic_items: list[MagicItemInstance],
                  instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    updated = magic_items[idx].model_copy(update={"equipped": False})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def use_charge(magic_items: list[MagicItemInstance],
               instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    inst = magic_items[idx]
    if inst.charges_remaining is None or inst.charges_remaining <= 0:
        raise NoCharges(f"{inst.catalog_id!r} has no charges left")
    updated = inst.model_copy(update={"charges_remaining": inst.charges_remaining - 1})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def reset_charges(magic_items: list[MagicItemInstance],
                  instance_id: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    inst = magic_items[idx]
    updated = inst.model_copy(update={"charges_remaining": inst.charges_max})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]


def remove_magic(magic_items: list[MagicItemInstance], gold: int,
                 instance_id: str, mode: str,
                 data: GameData) -> tuple[list[MagicItemInstance], int]:
    """drop = discard, no refund.  sell/refund refund only when cost_gp > 0
    (seed magic items are cost 0, so this is effectively drop for them)."""
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    idx = _index(magic_items, instance_id)
    catalog = data.items.get(magic_items[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = 0
    if cost > 0 and mode == "sell":
        refund = cost // 2
    elif cost > 0 and mode == "refund":
        refund = cost
    return [*magic_items[:idx], *magic_items[idx + 1:]], gold + refund


def set_magic_note(magic_items: list[MagicItemInstance], instance_id: str,
                   note: str) -> list[MagicItemInstance]:
    idx = _index(magic_items, instance_id)
    updated = magic_items[idx].model_copy(update={"note": note})
    return [*magic_items[:idx], updated, *magic_items[idx + 1:]]
