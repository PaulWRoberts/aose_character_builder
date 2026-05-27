"""Encumbrance and effective movement, using the OSE Advanced table.

Movement is **set** by the (armor class, weight band) pair — armour doesn't
subtract from a base rate, it picks a row of the table.  A Dwarf in chain
mail therefore walks at 30', not 60' minus 60'.

OSE Advanced movement (feet per turn), for the 120'-base human:

  Coins carried   | Unarmoured | Leather | Metal
  --------------- | ---------- | ------- | -----
  Up to 400 cn    |    120     |   90    |  60
  401 – 800       |     90     |   60    |  45
  801 – 1200      |     60     |   45    |  30
  1201 – 1600     |     30     |   15    |  15
  Over 1600       |      0     |    0    |   0

For demihuman races whose ``base_movement`` is below 120 (Dwarf, Halfling at
60'), every cell is scaled by ``base / 120`` and rounded down to the nearest
5'.  This matches the OSE Classic demihuman movement rates (Dwarf in chain
= 30', unencumbered = 60', etc.).

The three encumbrance modes pick which row/column of the table applies:
  * ``none``     – ignored, return race base outright
  * ``basic``    – armour class only; always uses band 0 (light)
  * ``detailed`` – uses the actual weight band from carried items

Carried weight is the sum of inventory ``weight_cn``.  Equipped items live in
``inventory`` already; we do **not** add their weight again from
``equipped`` / ``equipped_weapons``, which was a double-counting bug.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Armor, CharacterSpec


ArmorMovementClass = Literal["none", "leather", "metal"]

# Human-base table.  Index by (armor class, band).
_HUMAN_BASE = 120
_BAND_LABELS = ["≤ 400", "401–800", "801–1200", "1201–1600", "> 1600"]
_BAND_UPPER = [400, 800, 1200, 1600]  # > 1600 → band 4 (immobile)
_TABLE_HUMAN: dict[tuple[str, int], int] = {
    ("none", 0): 120, ("none", 1): 90, ("none", 2): 60, ("none", 3): 30, ("none", 4): 0,
    ("leather", 0): 90, ("leather", 1): 60, ("leather", 2): 45, ("leather", 3): 15, ("leather", 4): 0,
    ("metal", 0): 60, ("metal", 1): 45, ("metal", 2): 30, ("metal", 3): 15, ("metal", 4): 0,
}


def _scale(human_rate: int, race_base: int) -> int:
    """Scale a 120'-base table cell to the race's actual base, rounded down
    to the nearest 5'."""
    if race_base == _HUMAN_BASE:
        return human_rate
    scaled = (human_rate * race_base) // _HUMAN_BASE
    return (scaled // 5) * 5


def weight_band(weight_cn: int) -> int:
    """Return 0–4 for the OSE weight band.  Band 4 means over-encumbered."""
    for i, upper in enumerate(_BAND_UPPER):
        if weight_cn <= upper:
            return i
    return 4


def band_label(band: int) -> str:
    return _BAND_LABELS[band]


def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Total weight in coins.

    Equipped items live inside ``inventory`` already; weight is counted once
    via the inventory list to avoid the previous double-count bug.  Stashed
    items (``spec.stashed``) explicitly DO NOT count — that's their whole
    purpose.

    Carried containers contribute their own ``weight_cn`` plus
    ``int(weight_multiplier * raw_contents_weight)``.  Stashed containers
    contribute zero.
    """
    from aose.models import Container

    total = 0
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn

    for c in spec.containers:
        if c.state != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue
        total += catalog.weight_cn
        raw = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        total += int(catalog.weight_multiplier * raw)

    return total


def armor_movement_class(spec: CharacterSpec, data: GameData) -> ArmorMovementClass:
    armor_id = spec.equipped.get("armor")
    if not armor_id:
        return "none"
    item = data.items.get(armor_id)
    if not isinstance(item, Armor) or item.is_shield:
        return "none"
    return item.movement_impact


def effective_movement(spec: CharacterSpec, data: GameData) -> int:
    """The exploration movement rate after encumbrance, in feet per turn."""
    base = data.races[spec.race_id].base_movement
    mode = spec.ruleset.encumbrance

    if mode == "none":
        return base

    armor_cls = armor_movement_class(spec, data)

    if mode == "basic":
        # Light band only — armour alone drives it.
        return _scale(_TABLE_HUMAN[(armor_cls, 0)], base)

    band = weight_band(carried_weight_cn(spec, data))
    return _scale(_TABLE_HUMAN[(armor_cls, band)], base)


# ── Public table-display structures for the sheet ──────────────────────────

class ThresholdRow(BaseModel):
    band: int
    label: str            # e.g. "≤ 400" or "1201–1600"
    movement_per_armor: dict[str, int]   # {"none": 60, "leather": 45, "metal": 30}
    is_current_band: bool


class EncumbranceTable(BaseModel):
    mode: Literal["none", "basic", "detailed"]
    armor_classes: list[str]    # ["none", "leather", "metal"] in row-display order
    rows: list[ThresholdRow]    # one row per band, or just band 0 in basic mode


def encumbrance_table(spec: CharacterSpec, data: GameData) -> EncumbranceTable | None:
    """Return the movement-threshold table for the sheet, or ``None`` when
    encumbrance is disabled.  ``rows`` is just one row in basic mode (the
    armour-only line) and four rows in detailed mode."""
    mode = spec.ruleset.encumbrance
    if mode == "none":
        return None

    base = data.races[spec.race_id].base_movement
    current_band = 0
    if mode == "detailed":
        current_band = weight_band(carried_weight_cn(spec, data))

    rows: list[ThresholdRow] = []
    bands = range(4) if mode == "detailed" else [0]
    for b in bands:
        rows.append(ThresholdRow(
            band=b,
            label=band_label(b),
            movement_per_armor={
                cls: _scale(_TABLE_HUMAN[(cls, b)], base)
                for cls in ("none", "leather", "metal")
            },
            is_current_band=(b == current_band),
        ))

    return EncumbranceTable(
        mode=mode,
        armor_classes=["none", "leather", "metal"],
        rows=rows,
    )
