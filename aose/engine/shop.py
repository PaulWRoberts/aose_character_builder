"""Shop helpers: starting-gold rolls, category-grouped item listings, and the
buy/remove mutations that pair a price change with an inventory change.

The page templates are data-driven: ``shop_categories(data)`` returns whatever
categories are present in ``data.items``, so dropping a new YAML file with a
new ``category`` value (e.g. ``mounts``) makes that group appear in the UI
automatically.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Optional

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import Item


class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float


class ShopCategory(BaseModel):
    id: str
    name: str
    items: list[ShopItem]


class InventoryRow(BaseModel):
    id: str
    name: str
    count: int
    cost_gp: float     # unit price; refund amount equals this
    sell_gp: float     # 50% of cost, rounded down


def roll_starting_gold(rng: Optional[random.Random] = None) -> int:
    """3d6 × 10 gp — the AOSE/B/X starting-gold standard.  Range: 30–180 gp."""
    return roll("3d6", rng) * 10


def _category_label(cid: str) -> str:
    """Pretty default for a category id; users can edit YAML to introduce
    new categories without touching code."""
    return cid.replace("_", " ").title()


def shop_categories(data: GameData) -> list[ShopCategory]:
    """Group every item in ``data.items`` by its ``category`` field, sorted
    alphabetically.  Within a category, items are sorted by cost then name so
    the cheap stuff is at the top."""
    by_cat: dict[str, list[Item]] = {}
    for item in data.items.values():
        by_cat.setdefault(item.category, []).append(item)

    out: list[ShopCategory] = []
    for cid in sorted(by_cat):
        items = sorted(by_cat[cid], key=lambda i: (i.cost_gp, i.name))
        out.append(ShopCategory(
            id=cid,
            name=_category_label(cid),
            items=[
                ShopItem(id=i.id, name=i.name, category=i.category, cost_gp=i.cost_gp)
                for i in items
            ],
        ))
    return out


def inventory_rows(inventory: list[str], data: GameData) -> list[InventoryRow]:
    """Group repeated item ids into ``Item × N`` rows for display."""
    counts = Counter(inventory)
    out: list[InventoryRow] = []
    for item_id, count in counts.items():
        item = data.items.get(item_id)
        if item is None:
            # Stale id (item deleted from data after purchase) — surface it
            # rather than silently dropping the inventory entry.
            out.append(InventoryRow(
                id=item_id, name=item_id, count=count, cost_gp=0, sell_gp=0,
            ))
            continue
        out.append(InventoryRow(
            id=item_id,
            name=item.name,
            count=count,
            cost_gp=item.cost_gp,
            sell_gp=int(item.cost_gp // 2),
        ))
    out.sort(key=lambda r: r.name)
    return out


class InsufficientGold(ValueError):
    pass


class UnknownItem(ValueError):
    pass


def buy(inventory: list[str], gold: int, item_id: str,
        data: GameData) -> tuple[list[str], int]:
    """Append ``item_id`` to ``inventory`` and deduct its ``cost_gp`` from
    ``gold``.  Returns the new (inventory, gold) — does NOT mutate the inputs.
    Raises ``InsufficientGold`` or ``UnknownItem`` as appropriate."""
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    cost = int(item.cost_gp)  # rounded down for the gold balance
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand"
        )
    return ([*inventory, item_id], gold - cost)


REMOVE_MODES = ("drop", "sell", "refund")


def remove(inventory: list[str], gold: int, item_id: str, mode: str,
           data: GameData) -> tuple[list[str], int]:
    """Remove one instance of ``item_id`` from inventory.  ``mode`` controls
    the gold refund:

    * ``drop``   — no refund (you threw it away)
    * ``sell``   — half the listed cost (rounded down) — the standard B/X
                   "selling looted goods" rate
    * ``refund`` — full refund (you bought it by mistake)
    """
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} not in inventory")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")

    # Pop one instance (leave the others alone).
    new_inv = list(inventory)
    new_inv.remove(item_id)

    refund = 0
    if mode in ("sell", "refund"):
        item = data.items.get(item_id)
        cost = int(item.cost_gp) if item else 0
        refund = cost // 2 if mode == "sell" else cost

    return (new_inv, gold + refund)
