"""Encumbrance and effective movement.

Three modes (per ruleset.encumbrance):

* ``none``      — encumbrance is ignored, movement uses the race base outright.
* ``basic``     — armour type alone decides the movement category.  No item-by-
                  item tracking; the user trusts themselves not to overload.
* ``detailed``  — every carried/worn item contributes ``weight_cn`` to the
                  total load, and the OSE Advanced load table picks the
                  movement rate.

Numbers below follow the OSE Advanced encumbrance table:

  Detailed (total weight in coins, including armour):
      0-400 cn       no penalty                       (120' base preserved)
      401-800        -30' off the base
      801-1200       -60' off the base
      1201-1600      -90' off the base
      > 1600         immobile (returns 0)

  Basic (armour class drives it):
      unarmoured     no penalty
      leather        -30'
      metal          -60'

Demihuman races with a lower base_movement (Dwarves & Halflings at 60') get
the same reductions applied to their base — i.e. a chain-mailed Dwarf goes
to 0' in basic mode (60' - 60'), which matches the rulebook.
"""
from __future__ import annotations

from typing import Literal

from aose.data.loader import GameData
from aose.models import Armor, CharacterSpec


ArmorMovementClass = Literal["none", "leather", "metal"]

_BASIC_ARMOR_PENALTY = {"none": 0, "leather": 30, "metal": 60}


def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Total weight a character is carrying in coins (cn).

    Includes everything in inventory plus all equipped gear (armour, shield,
    weapons).  Items missing from the data set contribute 0 (defensive).
    """
    total = 0
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn
    for slot, item_id in spec.equipped.items():
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn
    for item_id in spec.equipped_weapons:
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn
    return total


def armor_movement_class(spec: CharacterSpec, data: GameData) -> ArmorMovementClass:
    """The character's armour class for movement purposes (none/leather/metal).

    Shields don't affect movement; only the worn-armour piece does.
    """
    armor_id = spec.equipped.get("armor")
    if not armor_id:
        return "none"
    item = data.items.get(armor_id)
    if not isinstance(item, Armor) or item.is_shield:
        return "none"
    return item.movement_impact


def _detailed_load_penalty(weight_cn: int) -> int | None:
    """Return the movement penalty (in feet) for a detailed-mode load.
    ``None`` means immobile."""
    if weight_cn <= 400:
        return 0
    if weight_cn <= 800:
        return 30
    if weight_cn <= 1200:
        return 60
    if weight_cn <= 1600:
        return 90
    return None  # over-encumbered


def effective_movement(spec: CharacterSpec, data: GameData) -> int:
    """The exploration-move value for the sheet, after encumbrance is applied."""
    base = data.races[spec.race_id].base_movement
    mode = spec.ruleset.encumbrance

    if mode == "none":
        return base

    armor_pen = _BASIC_ARMOR_PENALTY[armor_movement_class(spec, data)]

    if mode == "basic":
        return max(0, base - armor_pen)

    # detailed
    load_pen = _detailed_load_penalty(carried_weight_cn(spec, data))
    if load_pen is None:
        return 0
    # OSE Advanced: take the worse of armour and load penalty.
    return max(0, base - max(armor_pen, load_pen))
