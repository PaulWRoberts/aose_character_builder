"""Loader-time coercion of legacy character saves into the instance model.

Runs on the raw dict (needs GameData for stackable classification) BEFORE
CharacterSpec validation, because the legacy fields (inventory/stashed/
equipped/loaded_ammo/armor_tailored/contents/enchanted/ammo) no longer exist
on the model under extra='forbid'. Recurses into retainers. A save already
in the new shape (an ``items`` key, no legacy keys) passes through.
"""
from __future__ import annotations

import uuid

from aose.data.loader import GameData
from aose.models import Armor, Weapon

_LEGACY_KEYS = ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored",
                "enchanted", "ammo")
_KIND_SLOT = {"weapon": "main_hand", "armor": "armor", "shield": "off_hand"}


def _is_equippable(catalog_id: str, data: GameData) -> bool:
    return isinstance(data.items.get(catalog_id), (Weapon, Armor))


def _ench_kind(enchantment_id, data: GameData):
    ench = data.enchantments.get(enchantment_id) if enchantment_id else None
    return ench.kind if ench else None


def _new_instance(catalog_id: str, location: dict, count: int = 1) -> dict:
    return {"instance_id": uuid.uuid4().hex, "catalog_id": catalog_id,
            "location": location, "count": count}


def _coerce_spec(raw: dict, data: GameData) -> dict:
    if not isinstance(raw, dict):
        return raw
    legacy_present = any(k in raw for k in _LEGACY_KEYS) or _has_contents(raw)
    if not legacy_present:
        _coerce_retainers(raw, data)
        return raw

    equipped = raw.get("equipped") or {}          # slot -> catalog_id or enchanted instance_id
    loaded_ammo = raw.get("loaded_ammo") or {}     # weapon_key -> ammo instance id
    tailored = raw.get("armor_tailored", True)
    # slot lookup by catalog id (a catalog id may be equipped in >= 1 slot)
    slots_for: dict[str, list[str]] = {}
    for slot, cid in equipped.items():
        slots_for.setdefault(cid, []).append(slot)

    items: list[dict] = []

    def add_loose(cid: str, location: dict) -> None:
        equippable = _is_equippable(cid, data)
        inst = _new_instance(cid, location)
        if equippable:
            inst["count"] = 1
            if location.get("kind") == "carried" and slots_for.get(cid):
                inst["equip"] = slots_for[cid].pop(0)
            item = data.items.get(cid)
            if isinstance(item, Armor) and not item.is_shield:
                inst["tailored"] = tailored
            if cid in loaded_ammo:
                inst["loaded_ammo_id"] = loaded_ammo[cid]
            items.append(inst)
        else:
            for existing in items:
                if (existing["catalog_id"] == cid
                        and existing["location"] == location
                        and not _is_equippable(cid, data)):
                    existing["count"] += 1
                    return
            items.append(inst)

    for cid in raw.get("inventory", []):
        add_loose(cid, {"kind": "carried"})
    for cid in raw.get("stashed", []):
        add_loose(cid, {"kind": "stashed"})

    for coll, kind in (("containers", "container"), ("animals", "animal"),
                       ("vehicles", "vehicle")):
        for carrier in raw.get(coll, []):
            carrier_id = carrier.get("instance_id")
            for content_id in carrier.pop("contents", []) or []:
                add_loose(content_id, {"kind": kind, "id": carrier_id})

    # Fold enchanted list: each entry maps to an ItemInstance
    # The equip slot for a weapon/shield lived in equipped dict keyed by instance_id;
    # body armour used an "equipped" bool.
    slot_by_ench_id = {ref: slot for slot, ref in equipped.items()}
    for e in raw.get("enchanted", []) or []:
        loc = e.get("location") or {"kind": "carried"}
        slot = slot_by_ench_id.get(e["instance_id"])
        if slot is None and e.get("equipped"):
            slot = _KIND_SLOT.get(_ench_kind(e.get("enchantment_id"), data) or "")
        if slot is not None and loc.get("kind") != "carried":
            slot = None
        lid = loaded_ammo.get(e["instance_id"]) or loaded_ammo.get(e.get("base_id"))
        items.append({
            "instance_id": e["instance_id"],
            "catalog_id": e["base_id"],
            "enchantment_id": e.get("enchantment_id"),
            "location": loc,
            "count": 1,
            "equip": slot,
            "tailored": e.get("tailored", True),
            "loaded_ammo_id": lid,
            "charges_max": e.get("charges_max"),
            "charges_remaining": e.get("charges_remaining"),
            "extra_modifiers": e.get("extra_modifiers", []),
            "note": e.get("note", ""),
        })

    # Fold ammo list (stackable ItemInstances; preserve instance_id for loaded_ammo refs)
    for a in raw.get("ammo", []) or []:
        items.append({
            "instance_id": a["instance_id"],
            "catalog_id": a["base_id"],
            "enchantment_id": a.get("enchantment_id"),
            "location": a.get("location") or {"kind": "carried"},
            "count": a.get("count", 0),
        })

    raw["items"] = items
    for k in _LEGACY_KEYS:
        raw.pop(k, None)
    _coerce_retainers(raw, data)
    return raw


def _has_contents(raw: dict) -> bool:
    for coll in ("containers", "animals", "vehicles"):
        for carrier in raw.get(coll, []) or []:
            if isinstance(carrier, dict) and carrier.get("contents"):
                return True
    return False


def _coerce_retainers(raw: dict, data: GameData) -> None:
    for r in raw.get("retainers", []) or []:
        if isinstance(r, dict) and isinstance(r.get("spec"), dict):
            r["spec"] = _coerce_spec(r["spec"], data)


def migrate_legacy_items(raw: dict, data: GameData) -> dict:
    """Entry point: coerce a raw character dict (and its retainers) in place."""
    return _coerce_spec(raw, data)
