"""Single front door for per-item actions across the three inventory
substrates, composing the existing engines by ``category``.  Mirrors
``storage.move_thing``: differences between substrates live here as dispatch,
never as duplicated routes/templates.

  category == "item"      → plain ItemInstance   (spec.items, slot equip)
  category == "enchanted" → enchanted ItemInstance (spec.items, slot equip)
  category == "magic"     → MagicItemInstance    (spec.magic_items, toggle equip)

``owner`` selects the world the action runs in.  None / a "carried"/"stashed"
location means the PC itself; a ``retainer`` location runs against that
retainer's nested spec.  (Animal/vehicle "owners" never *equip* regular items —
that path is barding, handled by companions_engine — so they are not accepted
here.)
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.engine import equip as _equip_eng
from aose.engine import enchant as _enchant
from aose.engine import magic as _magic
from aose.engine import shop as _shop
from aose.models import CoinStack
from aose.models.storage import StorageLocation as _SL

ITEM_CATEGORIES = ("item", "enchanted")        # both are ItemInstance
ALL_CATEGORIES = ("item", "enchanted", "magic")


class InventoryActionError(ValueError):
    """Unknown category or illegal action (routes map to HTTP 400)."""


def _owning_spec(spec, owner):
    """The spec an action runs against: the PC, or a retainer's nested spec."""
    if owner is not None and getattr(owner, "kind", None) == "retainer":
        ret = next((r for r in spec.retainers if r.id == owner.id), None)
        if ret is None:
            raise InventoryActionError(f"no retainer {owner.id!r}")
        return ret.spec
    return spec


def _carried_gp(spec) -> int:
    return next((s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried"), 0)


def _set_carried_gp(spec, amount: int) -> None:
    carried = _SL(kind="carried")
    spec.coins = [s for s in spec.coins
                  if not (s.denom == "gp" and s.location == carried)]
    if amount > 0:
        spec.coins.append(CoinStack(denom="gp", count=amount))


def equip_thing(spec, category, instance_id, *, data: GameData, owner=None,
                slot=None, two_weapon=False, eligible=False,
                gargantua_1h_2h=False, allowed_weapons="all",
                allowed_armor="all", allow_shields=True) -> None:
    target = _owning_spec(spec, owner)
    if category in ITEM_CATEGORIES:
        _equip_eng.equip(
            target, instance_id, data=data, slot=slot,
            two_weapon=two_weapon, eligible=eligible,
            gargantua_1h_2h=gargantua_1h_2h, allowed_weapons=allowed_weapons,
            allowed_armor=allowed_armor, allow_shields=allow_shields)
    elif category == "magic":
        target.magic_items = _magic.equip_magic(target.magic_items, instance_id, data)
    else:
        raise InventoryActionError(f"unknown category {category!r}")


def unequip_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category in ITEM_CATEGORIES:
        _equip_eng.unequip(target, instance_id)
    elif category == "magic":
        target.magic_items = _magic.unequip_magic(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"unknown category {category!r}")


def sell_thing(spec, category, instance_id, mode: str, data: GameData,
               *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "item":
        _shop.sell_instance(target, instance_id, mode, data)
    elif category == "enchanted":
        # Enchanted items have no resale price; every mode is a drop.
        target.items = _enchant.remove(target.items, instance_id)
    elif category == "magic":
        gold = _carried_gp(target)
        target.magic_items, new_gold = _magic.remove_magic(
            target.magic_items, gold, instance_id, mode, data)
        _set_carried_gp(target, new_gold)
    else:
        raise InventoryActionError(f"unknown category {category!r}")


def use_charge_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.use_charge(target.items, instance_id)
    elif category == "magic":
        target.magic_items = _magic.use_charge(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"{category!r} has no charges")


def reset_charges_thing(spec, category, instance_id, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.reset_charges(target.items, instance_id)
    elif category == "magic":
        target.magic_items = _magic.reset_charges(target.magic_items, instance_id)
    else:
        raise InventoryActionError(f"{category!r} has no charges")


def set_note_thing(spec, category, instance_id, note: str, *, owner=None) -> None:
    target = _owning_spec(spec, owner)
    if category == "enchanted":
        target.items = _enchant.set_note(target.items, instance_id, note)
    elif category == "magic":
        target.magic_items = _magic.set_magic_note(target.magic_items, instance_id, note)
    else:
        raise InventoryActionError(f"{category!r} has no note")
