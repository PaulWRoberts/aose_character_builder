"""Shop helpers: starting-gold rolls, category-grouped item listings, and the
buy/remove mutations that pair a price change with an inventory change.

The page templates are data-driven: ``shop_categories(data)`` returns whatever
categories are present in ``data.items``, so dropping a new YAML file with a
new ``category`` value (e.g. ``mounts``) makes that group appear in the UI
automatically.
"""
from __future__ import annotations

import random
import uuid
from collections import Counter
from typing import Optional

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.models import Container, ContainerInstance, Item


class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    magic: bool = False


class ShopCategory(BaseModel):
    id: str
    name: str
    items: list[ShopItem]


class InventoryRow(BaseModel):
    id: str
    name: str
    count: int
    weight_cn: int = 0          # per-unit weight; row total = count * weight_cn
    cost_gp: float = 0          # unit price; refund amount equals this
    sell_gp: float = 0          # 50% of cost, rounded down
    equippable: bool = False     # weapon / armour / shield → True
    class_allowed: bool = True   # False when the character's class can't use it
    equipped_count: int = 0     # how many copies currently equipped (legacy flat view)


class ContainerView(BaseModel):
    """Per-instance container rendering data for the inventory partial."""
    instance_id: str
    catalog_id: str
    name: str
    state: str   # "carried" or "stashed"
    capacity_cn: int | None
    used_cn: int                 # raw sum of contents weight (for capacity)
    weight_multiplier: float
    own_weight_cn: int
    effective_weight_cn: int     # own + int(multiplier * used_cn) when carried, else 0
    contents: list[InventoryRow]


class InventoryView(BaseModel):
    """Three-state inventory split for the UI."""
    equipped: list[InventoryRow]   # items currently equipped (subset of "on person")
    carried: list[InventoryRow]    # on person but not equipped — contribute to weight
    stashed: list[InventoryRow]    # off-person stash — no weight contribution
    containers: list[ContainerView] = []


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
                ShopItem(
                    id=i.id, name=i.name, category=i.category,
                    cost_gp=i.cost_gp, weight_cn=i.weight_cn,
                    magic=i.magic,
                )
                for i in items
            ],
        ))
    return out


def _class_allows(item, allowed_weapons, allowed_armor, allow_shields) -> bool:
    """Whether the character's class may equip ``item`` given the allowance
    sets (or the ``"all"`` sentinel).  Non-equippable items are always True."""
    from aose.engine.proficiency import base_armor_id, base_weapon_id
    from aose.models import Armor, Weapon  # local to avoid circular import
    if isinstance(item, Weapon):
        return allowed_weapons == "all" or base_weapon_id(item) in allowed_weapons
    if isinstance(item, Armor):
        if item.is_shield:
            return allow_shields
        return allowed_armor == "all" or base_armor_id(item) in allowed_armor
    return True


def _build_row(item_id: str, count: int, data: GameData,
               allowed_weapons: "set[str] | str" = "all",
               allowed_armor: "set[str] | str" = "all",
               allow_shields: bool = True) -> InventoryRow:
    from aose.models import Armor, Weapon  # local to avoid circular import
    item = data.items.get(item_id)
    if item is None:
        # Stale id (item deleted from data after purchase) — surface it
        # rather than silently dropping the entry.
        return InventoryRow(id=item_id, name=item_id, count=count)
    return InventoryRow(
        id=item_id,
        name=item.name,
        count=count,
        weight_cn=item.weight_cn,
        cost_gp=item.cost_gp,
        sell_gp=int(item.cost_gp // 2),
        equippable=isinstance(item, (Weapon, Armor)),
        class_allowed=_class_allows(item, allowed_weapons, allowed_armor, allow_shields),
    )


def inventory_view(inventory: list[str], stashed: list[str],
                   equipped: dict[str, str], equipped_weapons: list[str],
                   containers: list[ContainerInstance] | None = None,
                   data: GameData = None,
                   allowed_weapons: "set[str] | str" = "all",
                   allowed_armor: "set[str] | str" = "all",
                   allow_shields: bool = True) -> InventoryView:
    """Three-section split of the character's loose items, plus a parallel
    ``containers`` list with each instance's contents already grouped.

    Items inside container ``contents`` are not surfaced in equipped/carried/
    stashed — they live only inside the container view.

    The optional allowance args mirror :func:`aose.engine.equip.equip`; each
    loose-item row gets a ``class_allowed`` flag so the UI can hide the Equip
    action for gear the character's class can't use.  Defaults leave every
    item allowed (backward-compatible).
    """
    containers = containers or []

    def row(item_id: str, n: int) -> InventoryRow:
        return _build_row(item_id, n, data,
                          allowed_weapons, allowed_armor, allow_shields)

    equipped_count: Counter[str] = Counter()
    for v in equipped.values():
        equipped_count[v] += 1
    for v in equipped_weapons:
        equipped_count[v] += 1

    inv_count: Counter[str] = Counter(inventory)
    stash_count: Counter[str] = Counter(stashed)

    eq_rows: list[InventoryRow] = []
    carried_rows: list[InventoryRow] = []
    for item_id, total in inv_count.items():
        eq_n = min(equipped_count[item_id], total)
        carried_n = total - eq_n
        if eq_n:
            eq_rows.append(row(item_id, eq_n))
        if carried_n:
            carried_rows.append(row(item_id, carried_n))

    stashed_rows = [row(i, n) for i, n in stash_count.items()]

    container_views: list[ContainerView] = []
    for c in containers:
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue   # stale catalog id; surface as zero-state
        rows_by_id: Counter[str] = Counter(c.contents)
        content_rows = [_build_row(i, n, data) for i, n in rows_by_id.items()]
        content_rows.sort(key=lambda r: r.name)
        raw_used = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in c.contents
        )
        effective = (
            catalog.weight_cn + int(catalog.weight_multiplier * raw_used)
            if c.state == "carried" else 0
        )
        container_views.append(ContainerView(
            instance_id=c.instance_id,
            catalog_id=c.catalog_id,
            name=catalog.name,
            state=c.state,
            capacity_cn=catalog.capacity_cn,
            used_cn=raw_used,
            weight_multiplier=catalog.weight_multiplier,
            own_weight_cn=catalog.weight_cn,
            effective_weight_cn=effective,
            contents=content_rows,
        ))

    eq_rows.sort(key=lambda r: r.name)
    carried_rows.sort(key=lambda r: r.name)
    stashed_rows.sort(key=lambda r: r.name)
    container_views.sort(key=lambda v: (v.state, v.name))
    return InventoryView(
        equipped=eq_rows, carried=carried_rows, stashed=stashed_rows,
        containers=container_views,
    )


def inventory_rows(inventory: list[str], data: GameData,
                   equipped: dict[str, str] | None = None,
                   equipped_weapons: list[str] | None = None) -> list[InventoryRow]:
    """Legacy flat-row API — preserved for callers that don't care about
    the three-state split.  Stash list isn't surfaced through this entry
    point; use :func:`inventory_view` instead."""
    view = inventory_view(
        inventory, [], equipped or {}, equipped_weapons or [], None, data,
    )
    # Merge equipped + carried into one row per item, with equipped_count
    # carrying the equipped half for callers using the legacy flat API.
    merged: dict[str, InventoryRow] = {}
    for row in view.carried:
        merged[row.id] = row.model_copy()
    for row in view.equipped:
        if row.id in merged:
            existing = merged[row.id]
            merged[row.id] = existing.model_copy(update={
                "count": existing.count + row.count,
                "equipped_count": row.count,
            })
        else:
            merged[row.id] = row.model_copy(update={"equipped_count": row.count})
    return sorted(merged.values(), key=lambda r: r.name)


class InsufficientGold(ValueError):
    pass


class UnknownItem(ValueError):
    pass


class ContainerFull(ValueError):
    pass


class ContainerNotEmpty(ValueError):
    pass


class UnknownContainer(ValueError):
    pass


def new_container_instance(catalog_id: str, data: GameData,
                           state: str = "carried") -> ContainerInstance:
    """Create a fresh ContainerInstance for the given catalog item.

    Validates that ``catalog_id`` is a Container in ``data.items``.  Returns a
    ContainerInstance with a uuid4-hex ``instance_id``.  Raises ``UnknownItem``
    if the id isn't in ``data.items`` and ``ValueError`` if the item exists
    but isn't a Container.
    """
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    return ContainerInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        state=state,  # type: ignore[arg-type]
        contents=[],
    )


def buy_container(containers: list[ContainerInstance], gold: int,
                  catalog_id: str, data: GameData
                  ) -> tuple[list[ContainerInstance], int]:
    """Like ``buy()`` but creates a ContainerInstance instead of appending to a
    flat inventory list.  Deducts ``cost_gp`` (rounded down) from ``gold``."""
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand"
        )
    return ([*containers, new_container_instance(catalog_id, data)], gold - cost)


def add_free_container(containers: list[ContainerInstance],
                       catalog_id: str, data: GameData
                       ) -> list[ContainerInstance]:
    """Append a new container instance without deducting gold (GM gift / loot)."""
    return [*containers, new_container_instance(catalog_id, data)]


def stash(inventory: list[str], stashed: list[str],
          equipped: dict[str, str], equipped_weapons: list[str],
          item_id: str, data: GameData) -> tuple[list[str], list[str], dict[str, str], list[str]]:
    """Move one copy of ``item_id`` from inventory to the stashed list.

    If the item is currently equipped, that equipped slot/instance is freed
    automatically — the item is going off-person.  Returns new
    ``(inventory, stashed, equipped, equipped_weapons)``.  Raises ValueError
    if the item isn't in inventory.
    """
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} is not in inventory")
    new_inv = list(inventory)
    new_inv.remove(item_id)
    new_stashed = [*stashed, item_id]

    new_eq = dict(equipped)
    for slot, equipped_id in list(new_eq.items()):
        if equipped_id == item_id:
            del new_eq[slot]
            break  # only one copy went off-person

    new_weapons = list(equipped_weapons)
    if item_id in new_weapons:
        new_weapons.remove(item_id)

    return new_inv, new_stashed, new_eq, new_weapons


def unstash(inventory: list[str], stashed: list[str],
            item_id: str, data: GameData) -> tuple[list[str], list[str]]:
    """Move one copy of ``item_id`` from stashed back into inventory."""
    if item_id not in stashed:
        raise ValueError(f"{item_id!r} is not in stash")
    new_stashed = list(stashed)
    new_stashed.remove(item_id)
    return [*inventory, item_id], new_stashed


def stow(inventory: list[str], stashed: list[str],
         containers: list[ContainerInstance],
         equipped: dict[str, str], equipped_weapons: list[str],
         instance_id: str, item_id: str, data: GameData,
         ) -> tuple[list[str], list[str], list[ContainerInstance]]:
    """Move one copy of ``item_id`` from ``inventory`` into the container with
    ``instance_id``.  Source is always inventory — to stow a stashed item,
    unstash it first; to stow an equipped item, unequip it first.

    Raises:
      * ``UnknownContainer`` if ``instance_id`` isn't in ``containers``.
      * ``ValueError("not in inventory")`` if ``item_id`` isn't carried.
      * ``ValueError("containers cannot be stowed")`` if ``item_id`` is itself
        a container catalog item (no nesting).
      * ``ValueError("item is equipped")`` if the item appears in ``equipped``
        or ``equipped_weapons`` (unequip first).
      * ``ContainerFull`` if adding the item's raw weight would exceed
        ``capacity_cn``.
    """
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")

    if item_id not in inventory:
        raise ValueError(f"{item_id!r} is not in inventory")

    item = data.items.get(item_id)
    if isinstance(item, Container):
        raise ValueError("containers cannot be stowed inside other containers")

    if item_id in equipped.values() or item_id in equipped_weapons:
        raise ValueError(f"{item_id!r} is equipped; unequip first")

    target = containers[idx]
    catalog = data.items[target.catalog_id]
    new_weight = item.weight_cn if item else 0
    if catalog.capacity_cn is not None:
        used = sum(
            (data.items[x].weight_cn if x in data.items else 0)
            for x in target.contents
        )
        if used + new_weight > catalog.capacity_cn:
            raise ContainerFull(
                f"{catalog.name} full: {used}/{catalog.capacity_cn} cn, "
                f"item adds {new_weight} cn"
            )

    new_inv = list(inventory)
    new_inv.remove(item_id)
    updated = target.model_copy(update={"contents": [*target.contents, item_id]})
    new_containers = [*containers[:idx], updated, *containers[idx + 1:]]
    return new_inv, stashed, new_containers


def take_out(inventory: list[str], stashed: list[str],
             containers: list[ContainerInstance],
             instance_id: str, item_id: str,
             ) -> tuple[list[str], list[str], list[ContainerInstance]]:
    """Remove one copy of ``item_id`` from the container's contents.

    Destination follows container state: a carried container puts the item
    back in ``inventory``; a stashed container puts it in ``stashed``.
    """
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]
    if item_id not in target.contents:
        raise ValueError(f"{item_id!r} not in container {instance_id!r}")

    new_contents = list(target.contents)
    new_contents.remove(item_id)
    updated = target.model_copy(update={"contents": new_contents})
    new_containers = [*containers[:idx], updated, *containers[idx + 1:]]

    if target.state == "carried":
        return [*inventory, item_id], stashed, new_containers
    return inventory, [*stashed, item_id], new_containers


def stash_container(containers: list[ContainerInstance],
                    instance_id: str) -> list[ContainerInstance]:
    """Flip a container's state to ``stashed``.  Contents follow implicitly —
    a stashed container's contents contribute zero to carried weight."""
    return _set_container_state(containers, instance_id, "stashed")


def unstash_container(containers: list[ContainerInstance],
                      instance_id: str) -> list[ContainerInstance]:
    """Flip a container's state to ``carried``."""
    return _set_container_state(containers, instance_id, "carried")


def _set_container_state(containers: list[ContainerInstance],
                         instance_id: str, new_state: str) -> list[ContainerInstance]:
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]
    if target.state == new_state:
        return list(containers)
    updated = target.model_copy(update={"state": new_state})
    return [*containers[:idx], updated, *containers[idx + 1:]]


def remove_container(containers: list[ContainerInstance], gold: int,
                     instance_id: str, mode: str, data: GameData,
                     ) -> tuple[list[ContainerInstance], int]:
    """Remove a container instance.

    * ``drop``    — instance + contents discarded, no refund.
    * ``sell``    — refunds half cost; raises ``ContainerNotEmpty`` if non-empty.
    * ``refund``  — refunds full cost; raises ``ContainerNotEmpty`` if non-empty.
    """
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")

    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]

    if mode in ("sell", "refund") and target.contents:
        raise ContainerNotEmpty(
            f"Cannot {mode} a container with contents — empty it first"
        )

    catalog = data.items.get(target.catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = 0
    if mode == "sell":
        refund = cost // 2
    elif mode == "refund":
        refund = cost

    new_containers = [*containers[:idx], *containers[idx + 1:]]
    return new_containers, gold + refund


def _bundle_count(item) -> int:
    """Units granted per purchase. Only AdventuringGear carries a bundle;
    every other item type behaves as a single unit."""
    return getattr(item, "bundle_count", 1)


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
    return ([*inventory, *([item_id] * _bundle_count(item))], gold - cost)


def add_free(inventory: list[str], item_id: str,
             data: GameData) -> list[str]:
    """Append ``item_id`` to ``inventory`` without changing gold — for items
    granted by the GM, found as loot, or otherwise acquired off-ledger.
    The complement of the ``drop`` removal mode."""
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    return [*inventory, item_id]


REMOVE_MODES = ("drop", "sell", "refund")


def _refund_amount(item_id: str, mode: str, data: GameData) -> int:
    if mode not in ("sell", "refund"):
        return 0
    item = data.items.get(item_id)
    cost = int(item.cost_gp) if item else 0
    return cost // 2 if mode == "sell" else cost


def remove(inventory: list[str], gold: int, item_id: str, mode: str,
           data: GameData,
           equipped: dict[str, str] | None = None,
           equipped_weapons: list[str] | None = None,
           ) -> tuple[list[str], int, dict[str, str], list[str]]:
    """Remove one instance of ``item_id`` from inventory.  ``mode`` controls
    the gold refund:

    * ``drop``   — no refund (you threw it away)
    * ``sell``   — half the listed cost (rounded down)
    * ``refund`` — full refund (you bought it by mistake)

    If the dropped instance was equipped, its slot/list entry is freed
    automatically (you can't keep wielding an item you just sold).  Pass
    ``equipped`` and ``equipped_weapons`` to enable that cleanup — they're
    optional for backward compatibility with the older two-tuple return.
    """
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} not in inventory")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")

    new_inv = list(inventory)
    new_inv.remove(item_id)

    new_eq = dict(equipped or {})
    new_weapons = list(equipped_weapons or [])

    # If the removed instance pushes equipped count past the remaining
    # inventory count, free up one equipped slot/instance.
    remaining = new_inv.count(item_id)
    eq_uses = sum(1 for v in new_eq.values() if v == item_id) + new_weapons.count(item_id)
    if eq_uses > remaining:
        # Try the slot dict first
        for slot, eid in list(new_eq.items()):
            if eid == item_id:
                del new_eq[slot]
                break
        else:
            # Otherwise drop one from weapons
            if item_id in new_weapons:
                new_weapons.remove(item_id)

    return new_inv, gold + _refund_amount(item_id, mode, data), new_eq, new_weapons


def remove_from_stash(stashed: list[str], gold: int, item_id: str, mode: str,
                      data: GameData) -> tuple[list[str], int]:
    """Drop / sell / refund an item that's in the stashed pile.  Stashed
    items aren't equipped (by definition), so no equipment cleanup is needed."""
    if item_id not in stashed:
        raise ValueError(f"{item_id!r} not in stash")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    new_stashed = list(stashed)
    new_stashed.remove(item_id)
    return new_stashed, gold + _refund_amount(item_id, mode, data)
