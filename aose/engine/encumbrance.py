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
``equipped`` (hand/body slots), which was a double-counting bug.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Armor, CharacterSpec


MAX_LOAD = 1600
TREASURE_CATEGORIES = {"magic_potions", "magic_rods_staves_wands", "scrolls"}

ArmorMovementClass = Literal["none", "leather", "metal"]

# AOSE detailed encumbrance bands (coin weights → movement).
_BAND_UPPER = [400, 600, 800, 1600]            # band 4 == over MAX_LOAD
_BAND_LABELS = ["≤ 400", "401–600", "601–800", "801–1600", "> 1600"]
_DETAILED_MOVE = [120, 90, 60, 30, 0]          # feet/turn per band


def weight_band(weight_cn: int) -> int:
    """Return 0–4 for the AOSE detailed band. Band 4 == over the 1,600 cap."""
    for i, upper in enumerate(_BAND_UPPER):
        if weight_cn <= upper:
            return i
    return 4


def band_label(band: int) -> str:
    return _BAND_LABELS[band]


def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Total tracked weight in coins = treasure + detailed-mode equipment.
    Used for the detailed band and as the sheet's carried-weight figure."""
    return treasure_weight_cn(spec, data) + equipment_weight_cn(spec, data)


def banding_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Weight used for movement banding: raw carried weight minus the active
    carry-capacity bonus, floored at zero.  The *displayed* carried weight stays
    raw — only the band/movement improves."""
    from aose.engine.magic import carry_capacity_bonus
    return max(0, carried_weight_cn(spec, data) - carry_capacity_bonus(spec, data))


def treasure_item_weight(item) -> int:
    """AOSE treasure-encumbrance weight for a carried magic item / scroll.
    Potions 10, wands 10, rods 20, staves 40, protection scrolls 1; anything
    else 0.  Derived from category + id prefix so catalog YAML needs no edits."""
    cat = getattr(item, "category", "")
    if cat == "magic_potions":
        return 10
    if cat == "scrolls":
        return 1
    if cat == "magic_rods_staves_wands":
        iid = getattr(item, "id", "")
        if iid.startswith("staff"):
            return 40
        if iid.startswith("rod"):
            return 20
        if iid.startswith("wand"):
            return 10
    return 0


def treasure_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Weight of tracked treasure: coins (1 cn each) + gems (1) + jewellery
    (10) + carried treasure magic items (potions/rods/staves/wands) + scrolls
    held as spell sources (1 cn each)."""
    from aose.engine import currency, valuables

    total = currency.coin_count(spec, carried_only=True) + valuables.valuables_weight_cn(spec)
    for mi in spec.magic_items:
        item = data.items.get(mi.catalog_id)
        if item is not None:
            total += treasure_item_weight(item)
    total += sum(1 for s in spec.spell_sources if s.kind == "scroll")
    return total


def equipment_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Detailed-mode equipment weight (everything that isn't tracked treasure):

      * carried weapons + armour by listed weight (enchanted armour keeps its
        weight_multiplier);
      * non-treasure magic items (rings, misc) and other carried items by their
        own weight;
      * a flat 80 cn when the character carries ANY adventuring gear —
        AdventuringGear items or carried containers. Gear's individual weights
        are never tracked (book RAW); the flat 80 is the whole of it.

    Treasure (coins/gems/jewellery/scrolls/potions/rods/staves/wands) is NOT
    counted here — it lives in treasure_weight_cn and contributes directly."""
    from aose.models import Weapon, AdventuringGear
    from aose.engine.enchant import resolve_instance

    total = 0
    has_gear = False
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is None:
            continue
        if isinstance(item, Armor):
            total += int(item.weight_cn * item.weight_multiplier)
        elif isinstance(item, Weapon):
            total += item.weight_cn
        elif isinstance(item, AdventuringGear):
            has_gear = True          # weight ignored — folded into the flat 80
        else:
            total += item.weight_cn  # poison, ammunition (0 cn), etc.

    for inst in spec.enchanted:
        resolved = resolve_instance(inst, data)
        if isinstance(resolved, Armor):
            total += int(resolved.weight_cn * resolved.weight_multiplier)
        elif isinstance(resolved, Weapon):
            total += resolved.weight_cn

    for mi in spec.magic_items:
        item = data.items.get(mi.catalog_id)
        if item is not None and item.category not in TREASURE_CATEGORIES:
            total += item.weight_cn

    # Carried containers contribute own weight + scaled contents.
    # They have listed weights (Bag of Holding has a 0.06 multiplier), so they
    # are NOT subsumed into the flat-80 abstraction.
    from aose.models import Container as _Container
    from aose.models.storage import StorageLocation
    for c in spec.containers:
        if c.location.kind != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, _Container):
            continue
        total += catalog.weight_cn
        raw = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        # coins (1cn) + gems (1cn) + jewellery (10cn) stowed in this container
        here = StorageLocation(kind="container", id=c.instance_id)
        raw += sum(s.count for s in spec.coins if s.location == here)
        raw += sum(g.count for g in spec.gems if g.location == here)
        raw += 10 * sum(1 for j in spec.jewellery if j.location == here)
        total += int(catalog.weight_multiplier * raw)

    if has_gear:
        total += 80
    return total


def armor_movement_class(spec: CharacterSpec, data: GameData) -> ArmorMovementClass:
    armor_id = spec.equipped.get("armor")
    if not armor_id:
        return "none"
    item = data.items.get(armor_id)
    if not isinstance(item, Armor) or item.is_shield:
        return "none"
    return item.movement_impact


_BASIC_TABLE = {
    ("none", False): 120, ("none", True): 90,
    ("leather", False): 90, ("leather", True): 60,
    ("metal", False): 60, ("metal", True): 30,
}


def _basic_movement(spec: CharacterSpec, data: GameData) -> int:
    """Basic encumbrance: armour worn × carrying-treasure toggle. Equipment
    weight is untracked; only the 1,600 treasure cap can immobilise."""
    if treasure_weight_cn(spec, data) > MAX_LOAD:
        return 0
    armor_cls = armor_movement_class(spec, data)
    return _BASIC_TABLE[(armor_cls, spec.carrying_treasure)]


def effective_movement(spec: CharacterSpec, data: GameData) -> int:
    """Exploration movement (feet/turn) after encumbrance."""
    base = data.races[spec.race_id].base_movement
    mode = spec.ruleset.encumbrance
    if mode == "none":
        return base
    if mode == "basic":
        return _basic_movement(spec, data)
    band = weight_band(banding_weight_cn(spec, data))
    return _DETAILED_MOVE[band]


# ── Public table-display structures for the sheet ──────────────────────────

class ThresholdRow(BaseModel):
    label: str                # armour name (basic) or band label (detailed)
    movements: list[int]      # basic: [no_treasure, carrying]; detailed: [rate]
    is_current_row: bool


class EncumbranceTable(BaseModel):
    mode: Literal["basic", "detailed"]
    columns: list[str]        # header labels for `movements`
    rows: list[ThresholdRow]
    current_col: int | None   # basic: active treasure column; detailed: None


_BASIC_ROWS = [("Unarmoured", "none"), ("Light armour", "leather"),
               ("Heavy armour", "metal")]


def encumbrance_table(spec: CharacterSpec, data: GameData) -> EncumbranceTable | None:
    """Movement table for the sheet, or None when encumbrance is off.
    Basic = 3 armour rows × 2 treasure columns; detailed = the four mobile
    weight bands (the >1,600 immobile band is omitted from the display)."""
    mode = spec.ruleset.encumbrance
    if mode == "none":
        return None

    if mode == "basic":
        current_cls = armor_movement_class(spec, data)
        rows = [
            ThresholdRow(
                label=name,
                movements=[_BASIC_TABLE[(cls, False)], _BASIC_TABLE[(cls, True)]],
                is_current_row=(cls == current_cls),
            )
            for name, cls in _BASIC_ROWS
        ]
        return EncumbranceTable(
            mode="basic",
            columns=["Without Treasure", "Carrying Treasure"],
            rows=rows,
            current_col=(1 if spec.carrying_treasure else 0),
        )

    current_band = weight_band(banding_weight_cn(spec, data))
    rows = [
        ThresholdRow(label=band_label(b), movements=[_DETAILED_MOVE[b]],
                     is_current_row=(b == current_band))
        for b in range(4)
    ]
    return EncumbranceTable(mode="detailed", columns=["Movement"],
                            rows=rows, current_col=None)
