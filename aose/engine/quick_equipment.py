"""Quick Equipment generator (Carcass Crawler, Gavin Norman).

Rolls a class-appropriate starting kit (armour, weapons, ammo, gear, gold) onto a
fresh QuickKit, which apply_kit() writes onto a CharacterSpec. Pure + injectable
RNG. Classes present in data.quick_equipment["classes"] use their authored kit;
the rest use a proficiency heuristic (see _heuristic_fill). Cycle-free: models,
loader, dice, proficiency, equip only.
"""
from __future__ import annotations

import random
from typing import Optional

from pydantic import BaseModel, Field

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.engine.equip import equip as equip_inst, hand_cost
from aose.engine.proficiency import allowed_armor_ids, allowed_weapon_ids
from aose.models import Armor, CharacterSpec, Weapon


class QuickKit(BaseModel):
    inventory: list[str] = Field(default_factory=list)    # catalog_ids (non-ammo, non-container)
    equips: dict[str, str] = Field(default_factory=dict)  # slot -> catalog_id intentions
    ammo: list[dict] = Field(default_factory=list)        # [{"base_id": str, "count": int}]
    gold: int = 0


# Basic equipment every character receives.
_BASIC = ["backpack", "tinder_box", "waterskin"]

# Ammo each launcher needs, for heuristic grants.
_LAUNCHER_AMMO = {"short_bow": "arrow", "long_bow": "arrow",
                  "crossbow": "crossbow_bolt", "sling": "sling_stone"}


def _apply_grants(grants: list[dict], kit: QuickKit, *,
                  pending_armor: list, pending_shield: list) -> None:
    """Apply a table row's grants to the kit. Armour/shield are deferred to the
    caller (equipped after all weapons are known, for the hand budget)."""
    for g in grants:
        if "id" in g:
            kit.inventory.extend([g["id"]] * int(g.get("n", 1)))
        elif "ammo" in g:
            kit.ammo.append({"base_id": g["ammo"], "count": int(g.get("n", 1))})
        elif "armor" in g:
            pending_armor.append(g["armor"])
        elif g.get("shield"):
            pending_shield.append("shield")


def _roll_armour_row(spec, tables: dict, rng) -> list[dict]:
    """Resolve an armour spec to a chosen table row (list of grants).

    spec forms: "armour_d6" | {table, die?, modifier?, ignore_shields?}
                | {fixed: <armor_id>} | "none".
    """
    if spec == "none" or spec is None:
        return []
    if isinstance(spec, dict) and "fixed" in spec:
        return [{"armor": spec["fixed"]}]
    table_name = spec if isinstance(spec, str) else spec.get("table", "armour_d6")
    rows = tables[table_name]
    die = (spec.get("die") if isinstance(spec, dict) else None) or "1d6"
    modifier = (spec.get("modifier") if isinstance(spec, dict) else 0) or 0
    idx = roll(die, rng) + modifier            # 1-based table position
    idx = max(1, min(idx, len(rows)))
    row = list(rows[idx - 1])
    if isinstance(spec, dict) and spec.get("ignore_shields"):
        row = [g for g in row if not g.get("shield")]
    return row


def _roll_weapons(wspec: dict, tables: dict, kit: QuickKit, rng) -> None:
    if "fixed" in wspec:
        for wid in wspec["fixed"]:
            kit.inventory.append(wid)
        return
    rows = tables[wspec["table"]]
    pa, ps = [], []  # weapon tables never grant armour/shield
    for _ in range(int(wspec.get("rolls", 1))):
        chosen = rows[roll(f"1d{len(rows)}", rng) - 1]
        _apply_grants(chosen, kit, pending_armor=pa, pending_shield=ps)


def _equip_loadout(kit: QuickKit, pending_armor: list, pending_shield: list,
                   data: GameData) -> None:
    """Record equip intentions in kit.equips (slot -> catalog_id).
    apply_kit() does the actual per-instance equipping later."""
    for armor_id in pending_armor[:1]:
        kit.inventory.append(armor_id)
        item = data.items.get(armor_id)
        if isinstance(item, Armor) and not item.is_shield:
            kit.equips["armor"] = armor_id

    # main hand: first melee weapon, else first weapon present in inventory.
    weapons = [i for i in kit.inventory if isinstance(data.items.get(i), Weapon)]
    melee = [i for i in weapons if data.items[i].melee]
    main = (melee or weapons or [None])[0]
    if main is not None:
        kit.equips["main_hand"] = main

    # shield only if a hand remains free (main not two-handed).
    if pending_shield:
        kit.inventory.append("shield")
        main_item = data.items.get(kit.equips.get("main_hand"))
        used = hand_cost(main_item, gargantua_1h_2h=False) if main_item else 0
        if used < 2:
            kit.equips["off_hand"] = "shield"


def _heuristic_armour_row(cls, data, tables, rng) -> list[dict]:
    """Filter the d6 armour table to rows the class can wear, then roll among
    the survivors. Shield rows kept only when the class allows shields."""
    allowed = allowed_armor_ids([cls], data)
    rows = []
    for row in tables.get("armour_d6", []):
        armor_id = next((g["armor"] for g in row if "armor" in g), None)
        has_shield = any(g.get("shield") for g in row)
        if allowed != "all" and armor_id not in allowed:
            continue
        if has_shield and not cls.shields_allowed:
            continue
        rows.append(row)
    if not rows:
        return []
    return list(rows[roll(f"1d{len(rows)}", rng) - 1])


def _heuristic_weapons(cls, data, kit: QuickKit, rng) -> None:
    """All-weapons → general d12 twice. A limited set: >2 ids → custom uniform
    roll twice; 1-2 ids → grant them outright. Ammo added for launchers."""
    allowed = allowed_weapon_ids([cls], data)
    tables = data.quick_equipment.get("tables", {})

    def _grant_weapon(wid: str) -> None:
        kit.inventory.append(wid)
        ammo = _LAUNCHER_AMMO.get(wid)
        if ammo:
            kit.ammo.append({"base_id": ammo, "count": 20})

    if allowed == "all":
        rows = tables["general"]
        for _ in range(2):
            row = rows[roll(f"1d{len(rows)}", rng) - 1]
            _apply_grants(row, kit, pending_armor=[], pending_shield=[])
        return
    ids = sorted(allowed)
    if len(ids) <= 2:
        for wid in ids:
            _grant_weapon(wid)
        return
    for _ in range(2):
        _grant_weapon(ids[roll(f"1d{len(ids)}", rng) - 1])


def _heuristic_fill(class_id: str, data: GameData, kit: QuickKit,
                    tables: dict, rng) -> None:
    cls = data.classes.get(class_id)
    if cls is None:
        kit.inventory.append("dagger")
        return
    pending_armor: list = []
    pending_shield: list = []
    armour_row = _heuristic_armour_row(cls, data, tables, rng)
    _apply_grants(armour_row, kit, pending_armor=pending_armor,
                  pending_shield=pending_shield)
    _heuristic_weapons(cls, data, kit, rng)
    if not any(isinstance(data.items.get(i), Weapon) for i in kit.inventory):
        kit.inventory.append("dagger")   # guarantee at least one weapon
    _equip_loadout(kit, pending_armor, pending_shield, data)


def roll_kit(class_id: str, data: GameData,
             rng: Optional[random.Random] = None) -> QuickKit:
    rng = rng or random.Random()
    kit = QuickKit()
    # 1. basic gear + variable quantities + gold
    kit.inventory.extend(_BASIC)
    kit.inventory.extend(["torch"] * roll("1d6", rng))
    kit.inventory.extend(["iron_rations"] * roll("1d6", rng))
    kit.gold = roll("3d6", rng)

    classes = data.quick_equipment.get("classes", {})
    tables = data.quick_equipment.get("tables", {})

    if class_id in classes:
        kit_spec = classes[class_id]
        pending_armor: list = []
        pending_shield: list = []
        armour_row = _roll_armour_row(kit_spec.get("armour", "none"), tables, rng)
        _apply_grants(armour_row, kit, pending_armor=pending_armor,
                      pending_shield=pending_shield)
        _roll_weapons(kit_spec["weapons"], tables, kit, rng)
        for extra in kit_spec.get("extras", []):
            kit.inventory.append(extra)
        _equip_loadout(kit, pending_armor, pending_shield, data)
    else:
        _heuristic_fill(class_id, data, kit, tables, rng)

    # 2. adventuring gear: roll 1d12 twice from the gear table
    ag = tables.get("adventuring_gear", [])
    if ag:
        for _ in range(2):
            row = ag[roll(f"1d{len(ag)}", rng) - 1]
            _apply_grants(row, kit, pending_armor=[], pending_shield=[])
    return kit


def apply_kit(spec: CharacterSpec, kit: QuickKit, data: GameData) -> None:
    """Write a rolled kit onto a CharacterSpec. Container items are promoted to
    ContainerInstances; everything else becomes a flat ItemInstance in spec.items."""
    from aose.models import CoinStack, Container
    from aose.models.storage import StorageLocation
    from aose.engine.shop import new_container_instance
    from aose.engine.equip import WieldError

    from aose.engine.storage import add_item

    CARRIED = StorageLocation(kind="carried")

    # Build ItemInstances for each catalog_id in kit.inventory (merging stackables).
    for item_id in kit.inventory:
        item = data.items.get(item_id)
        if isinstance(item, Container):
            spec.containers.append(new_container_instance(item_id, data))
        else:
            add_item(spec, item_id, 1, CARRIED, data)

    # Ammo grants (merge into the resident ammo stack of that catalog id).
    for grant in kit.ammo:
        add_item(spec, grant["base_id"], int(grant["count"]), CARRIED, data)

    # Apply equip intentions: for each slot, find the first unequipped carried
    # instance with the matching catalog_id and equip it.
    for slot, catalog_id in kit.equips.items():
        target_inst = next(
            (i for i in spec.items
             if i.catalog_id == catalog_id and i.location == CARRIED and i.equip is None),
            None,
        )
        if target_inst is None:
            continue
        try:
            equip_inst(spec, target_inst.instance_id, data=data,
                       slot=slot if slot in ("main_hand", "off_hand") else None)
        except (ValueError, WieldError):
            pass

    if kit.gold > 0:
        spec.coins = [CoinStack(denom="gp", count=kit.gold)]
