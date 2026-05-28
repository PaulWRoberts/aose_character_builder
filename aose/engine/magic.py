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
from aose.models import Ability, CharacterSpec, MagicItem, MagicItemInstance, Modifier


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
    """Catalog modifiers + extra_modifiers from every EQUIPPED magic item."""
    out: list[Modifier] = []
    for inst in spec.magic_items:
        if not inst.equipped:
            continue
        catalog = data.items.get(inst.catalog_id)
        if isinstance(catalog, MagicItem):
            out.extend(catalog.modifiers)
        out.extend(inst.extra_modifiers)
    return out


def effective_abilities(spec: CharacterSpec, data: GameData) -> dict[Ability, int]:
    """``spec.abilities`` with every ``ability:*`` modifier applied."""
    mods = active_modifiers(spec, data)
    scores = dict(spec.abilities)
    for ab in Ability:
        target = f"ability:{ab.value}"
        if any(m.target == target for m in mods):
            scores[ab] = apply_modifiers(scores[ab], mods, target)
    return scores


def carry_capacity_bonus(spec: CharacterSpec, data: GameData) -> int:
    """Effective bonus carrying capacity in cn from active modifiers.

    ``add`` accumulates; a literal ``set`` (rare) overrides the running total.
    """
    return apply_modifiers(0, active_modifiers(spec, data), "carry_capacity")


def needs_instance(item) -> bool:
    """Whether a catalog item must be tracked as a MagicItemInstance (because
    it carries mutable per-instance state: equippable or charged)."""
    return isinstance(item, MagicItem) and (
        item.equippable or item.max_charges is not None or item.charge_dice is not None
    )
