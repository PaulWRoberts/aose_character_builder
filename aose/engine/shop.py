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

from pydantic import BaseModel, Field

from aose.data.loader import GameData
from aose.engine.currency import RATES, DENOMINATIONS
from aose.engine.detail import DetailCard, item_card
from aose.engine.dice import roll
from aose.engine.sources import content_enabled
from aose.models import Container, ContainerInstance, Item, RuleSet
from aose.models.storage import StorageLocation


class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    magic: bool = False
    bundle_count: int = 1
    detail: DetailCard | None = None


class ShopCategory(BaseModel):
    id: str
    name: str
    items: list[ShopItem]


class InventoryRow(BaseModel):
    id: str
    name: str
    description: str = ""        # catalog description (for the per-item detail modal)
    count: int
    weight_cn: int = 0          # per-unit weight; row total = count * weight_cn
    cost_gp: float = 0          # bundle price (what the shop charges per purchase)
    sell_gp: float = 0          # per-unit half price (may be 0 for cheap bundles)
    equippable: bool = False     # weapon / armour / shield → True
    class_allowed: bool = True   # False when the character's class can't use it
    equipped_count: int = 0     # how many copies currently equipped (legacy flat view)
    bundle_count: int = 1        # units the shop sells per purchase
    can_refund: bool = True      # True when count >= bundle_count
    can_off_hand: bool = False   # two_weapon rule on + eligible + weapon passes test
    off_hand_blocked: bool = False  # can_off_hand but off hand already occupied
    detail: DetailCard | None = None   # structured card for the inline expander


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
    detail: DetailCard | None = None   # catalog item card for the per-container modal


class CoinRow(BaseModel):
    denom: str
    count: int


class TopLevelGroup(BaseModel):
    """One inventory pane — Carried, Stashed, or a carrier/retainer."""
    kind: str                             # carried | stashed | animal | vehicle | retainer
    id: str | None = None                 # carrier/retainer instance_id; None for person buckets
    label: str                            # display name
    has_equipped: bool = False
    equipped: list[InventoryRow] = Field(default_factory=list)
    # Rich equipped display for the live sheet pane. PC + retainers fill
    # equipped_attacks (AttackProfile); equipped_worn holds armour/shield rows
    # (EquippedRow); equipped_magic holds worn magic rows (MagicItemView).
    equipped_attacks: list = Field(default_factory=list)
    equipped_worn: list = Field(default_factory=list)
    equipped_magic: list = Field(default_factory=list)
    loose: list[InventoryRow] = Field(default_factory=list)
    coins: list[CoinRow] = Field(default_factory=list)
    treasure_gems: list = Field(default_factory=list)       # GemRow — list to avoid circular import
    treasure_jewellery: list = Field(default_factory=list)  # JewelleryRow
    containers: list[ContainerView] = Field(default_factory=list)


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


def shop_categories(data: GameData, ruleset: RuleSet | None = None) -> list[ShopCategory]:
    """Group every item in ``data.items`` by its ``category`` field, sorted
    alphabetically.  Within a category, items are sorted by cost then name so
    the cheap stuff is at the top.  When ``ruleset`` is given, items from a
    disabled source are omitted."""
    by_cat: dict[str, list[Item]] = {}
    for item in data.items.values():
        if ruleset is not None:
            is_magic = getattr(item, "item_type", None) == "magic" or getattr(
                item, "magic", False
            )
            category = "magic_items" if is_magic else "equipment"
            if not content_enabled(item.source, category, ruleset):
                continue
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
                    magic=i.magic, bundle_count=_bundle_count(i),
                    detail=item_card(i),
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
               allow_shields: bool = True,
               two_weapon: bool = False, eligible: bool = False,
               off_full: bool = False) -> InventoryRow:
    from aose.engine.equip import off_hand_eligible
    from aose.models import Armor, Weapon  # local to avoid circular import
    item = data.items.get(item_id)
    if item is None:
        return InventoryRow(id=item_id, name=item_id, count=count)
    bundle = _bundle_count(item)
    can_off = (two_weapon and eligible and isinstance(item, Weapon)
               and off_hand_eligible(item))
    return InventoryRow(
        id=item_id,
        name=item.name,
        description=getattr(item, "description", "") or "",
        count=count,
        weight_cn=item.weight_cn,
        cost_gp=item.cost_gp,
        sell_gp=int((item.cost_gp / bundle) / 2),
        equippable=isinstance(item, (Weapon, Armor)),
        class_allowed=_class_allows(item, allowed_weapons, allowed_armor, allow_shields),
        bundle_count=bundle,
        can_refund=count >= bundle,
        can_off_hand=can_off,
        off_hand_blocked=can_off and off_full,
        detail=item_card(item),
    )


def inventory_view(inventory: list[str], stashed: list[str],
                   equipped: dict[str, str],
                   containers: list[ContainerInstance] | None = None,
                   data: GameData = None,
                   allowed_weapons: "set[str] | str" = "all",
                   allowed_armor: "set[str] | str" = "all",
                   allow_shields: bool = True,
                   two_weapon: bool = False,
                   eligible: bool = False,
                   gargantua_1h_2h: bool = False) -> InventoryView:
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
    off_full = bool(equipped.get("off_hand"))

    def row(item_id: str, n: int) -> InventoryRow:
        return _build_row(item_id, n, data,
                          allowed_weapons, allowed_armor, allow_shields,
                          two_weapon=two_weapon, eligible=eligible,
                          off_full=off_full)

    equipped_count: Counter[str] = Counter()
    for v in equipped.values():
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
        if c.location.kind not in ("carried", "stashed"):
            continue   # rendered inside its carrier's card, not the loose list
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
        loc_kind = c.location.kind
        effective = (
            catalog.weight_cn + int(catalog.weight_multiplier * raw_used)
            if loc_kind == "carried" else 0
        )
        container_views.append(ContainerView(
            instance_id=c.instance_id,
            catalog_id=c.catalog_id,
            name=catalog.name,
            state=loc_kind,
            capacity_cn=catalog.capacity_cn,
            used_cn=raw_used,
            weight_multiplier=catalog.weight_multiplier,
            own_weight_cn=catalog.weight_cn,
            effective_weight_cn=effective,
            contents=content_rows,
            detail=item_card(catalog),
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
                   equipped: dict[str, str] | None = None) -> list[InventoryRow]:
    """Legacy flat-row API — preserved for callers that don't care about
    the three-state split.  Stash list isn't surfaced through this entry
    point; use :func:`inventory_view` instead."""
    view = inventory_view(
        inventory, [], equipped or {}, None, data,
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


class InsufficientFunds(ValueError):
    """Not enough carried coins to cover a purchase (routes map to HTTP 400)."""


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
                           state: str = "carried",
                           location: "StorageLocation | None" = None) -> ContainerInstance:
    """Create a fresh ContainerInstance for the given catalog item.

    Validates that ``catalog_id`` is a Container. ``location`` (preferred) places
    it at any non-container location; the legacy ``state`` kwarg still works for
    person buckets.
    """
    item = data.items.get(catalog_id)
    if item is None:
        raise UnknownItem(f"No item with id {catalog_id!r}")
    if not isinstance(item, Container):
        raise ValueError(f"{catalog_id!r} is not a container")
    if location is None:
        location = StorageLocation(kind=state)  # type: ignore[arg-type]
    return ContainerInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        location=location,
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
          equipped: dict[str, str],
          item_id: str, data: GameData) -> tuple[list[str], list[str], dict[str, str]]:
    """Move one copy of ``item_id`` from inventory to the stashed list.

    If the item is currently equipped, that slot is freed automatically.
    Returns new ``(inventory, stashed, equipped)``.  Raises ValueError if the
    item isn't in inventory.
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

    return new_inv, new_stashed, new_eq


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
         equipped: dict[str, str],
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
        (unequip first).
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

    if item_id in equipped.values():
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

    if target.location.kind == "carried":
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
    from aose.models.storage import StorageLocation
    idx = next((i for i, c in enumerate(containers) if c.instance_id == instance_id), None)
    if idx is None:
        raise UnknownContainer(f"No container with id {instance_id!r}")
    target = containers[idx]
    new_loc = StorageLocation(kind=new_state)   # type: ignore[arg-type]
    if target.location == new_loc:
        return list(containers)
    updated = target.model_copy(update={"location": new_loc})
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


def _removal_gold(item_id: str, mode: str, data: GameData) -> int:
    """Gold returned for a removal mode.

    * ``sell``   — per-unit half price ``int((cost_gp / bundle_count) / 2)``
    * ``refund`` — the full bundle price ``int(cost_gp)``
    * ``drop``   — nothing
    """
    item = data.items.get(item_id)
    if item is None or mode == "drop":
        return 0
    cost = item.cost_gp
    if mode == "refund":
        return int(cost)
    # sell: per-unit, halved, floored
    return int((cost / _bundle_count(item)) / 2)


def remove(inventory: list[str], gold: int, item_id: str, mode: str,
           data: GameData,
           equipped: dict[str, str] | None = None,
           ) -> tuple[list[str], int, dict[str, str]]:
    """Remove one instance of ``item_id`` from inventory.  ``mode`` controls
    the gold refund:

    * ``drop``   — no refund (you threw it away)
    * ``sell``   — per-unit half price (rounded down; may be 0)
    * ``refund`` — remove a full bundle_count stack, return full cost

    If the dropped instance was equipped, its slot is freed automatically.
    Pass ``equipped`` to enable that cleanup — optional for backward compat.
    """
    if item_id not in inventory:
        raise ValueError(f"{item_id!r} not in inventory")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")

    item = data.items.get(item_id)
    bundle = _bundle_count(item)

    new_inv = list(inventory)
    if mode == "refund" and bundle > 1:
        if new_inv.count(item_id) < bundle:
            raise ValueError(
                f"Cannot refund {item_id!r}: need a full stack of {bundle}"
            )
        for _ in range(bundle):
            new_inv.remove(item_id)
    else:
        new_inv.remove(item_id)

    new_eq = dict(equipped or {})

    # If removal pushed equipped count past remaining inventory, free a slot.
    remaining = new_inv.count(item_id)
    eq_uses = sum(1 for v in new_eq.values() if v == item_id)
    while eq_uses > remaining:
        for slot, eid in list(new_eq.items()):
            if eid == item_id:
                del new_eq[slot]
                break
        else:
            break
        eq_uses -= 1

    return new_inv, gold + _removal_gold(item_id, mode, data), new_eq


def remove_from_stash(stashed: list[str], gold: int, item_id: str, mode: str,
                      data: GameData) -> tuple[list[str], int]:
    """Drop / sell / refund a stashed item.  Refund removes a full bundle."""
    if item_id not in stashed:
        raise ValueError(f"{item_id!r} not in stash")
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}; want one of {REMOVE_MODES}")
    item = data.items.get(item_id)
    bundle = _bundle_count(item)
    new_stashed = list(stashed)
    if mode == "refund" and bundle > 1:
        if new_stashed.count(item_id) < bundle:
            raise ValueError(
                f"Cannot refund {item_id!r}: need a full stack of {bundle}"
            )
        for _ in range(bundle):
            new_stashed.remove(item_id)
    else:
        new_stashed.remove(item_id)
    return new_stashed, gold + _removal_gold(item_id, mode, data)


# ── Coin-based spend (Task 10) ──────────────────────────────────────────────

_ORDER_LOW = ["cp", "sp", "ep", "gp", "pp"]   # ascending value
_VALS = [RATES[d] for d in _ORDER_LOW]        # [1, 10, 50, 100, 500]


def _exact_payment(avail: dict[str, int], cost_cp: int) -> dict[str, int] | None:
    """Largest-low-coin exact payment of ``cost_cp`` from ``avail``, or None."""
    n = len(_ORDER_LOW)
    maxval = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        maxval[i] = maxval[i + 1] + avail.get(_ORDER_LOW[i], 0) * _VALS[i]

    def rec(i, remaining, chosen):
        if remaining == 0:
            return dict(chosen)
        if i == n:
            return None
        v = _VALS[i]
        hi = min(avail.get(_ORDER_LOW[i], 0), remaining // v)
        for k in range(hi, -1, -1):
            rem2 = remaining - k * v
            if rem2 <= maxval[i + 1]:
                chosen[_ORDER_LOW[i]] = k
                got = rec(i + 1, rem2, chosen)
                if got is not None:
                    return got
        chosen[_ORDER_LOW[i]] = 0
        return None

    return rec(0, cost_cp, {})


def _payment_plan(avail: dict[str, int], cost_cp: int) -> tuple[dict[str, int], int]:
    """Return (spend_by_denom, change_cp). Tries exact first, then smallest
    whole-gp overshoot. Raises InsufficientFunds."""
    total = sum(avail.get(d, 0) * RATES[d] for d in DENOMINATIONS)
    if total < cost_cp:
        raise InsufficientFunds(
            f"need {cost_cp // 100} gp; only {total // 100} gp on hand"
        )
    j = 0
    while cost_cp + 100 * j <= total:
        sol = _exact_payment(avail, cost_cp + 100 * j)
        if sol is not None:
            return sol, 100 * j
        j += 1
    raise InsufficientFunds("cannot pay without breaking coins — convert first")


def spend(spec, cost_gp: int) -> None:
    """Spend ``cost_gp`` from CARRIED coins, lowest denomination first.
    If exact payment is impossible, pays the smallest whole-gp overshoot
    and returns the change as carried gp. Mutates ``spec.coins`` in place."""
    from aose.engine import storage as _storage
    carried = StorageLocation(kind="carried")
    avail = {c.denom: c.count for c in spec.coins if c.location == carried}
    spend_by, change_cp = _payment_plan(avail, cost_gp * 100)
    for denom, k in spend_by.items():
        if k:
            _storage._take_coins(spec, denom, k, carried)
    if change_cp:
        _storage._add_coins(spec, "gp", change_cp // 100, carried)


def buy_item(spec, item_id: str, data: GameData) -> None:
    """Buy one bundle of ``item_id`` onto carried inventory, spending carried coins."""
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    spend(spec, int(item.cost_gp))
    spec.inventory.extend([item_id] * _bundle_count(item))


def sell_item(spec, item_id: str, mode: str, data: GameData) -> None:
    """Remove one instance from carried inventory; credit carried gp per mode."""
    from aose.engine import storage as _storage
    new_inv, credit, new_eq = remove(spec.inventory, 0, item_id, mode, data, spec.equipped)
    spec.inventory[:] = new_inv
    spec.equipped.clear()
    spec.equipped.update(new_eq)
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))


def sell_container(spec, instance_id: str, mode: str, data: GameData) -> None:
    """Remove a container instance; credit carried gp per mode."""
    from aose.engine import storage as _storage
    new_containers, credit = remove_container(
        spec.containers, 0, instance_id, mode, data)
    spec.containers[:] = new_containers
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))


def sell_from_stash(spec, item_id: str, mode: str, data: GameData) -> None:
    """Remove one stashed item; credit carried gp per mode."""
    from aose.engine import storage as _storage
    new_stash, credit = remove_from_stash(spec.stashed, 0, item_id, mode, data)
    spec.stashed[:] = new_stash
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
