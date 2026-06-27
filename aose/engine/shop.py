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
    instance_id: str = ""        # ItemInstance.instance_id — empty for rows built without spec
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
    # Pointer-type items stowed in this container (location=container/<instance_id>)
    stowed_coins: list = Field(default_factory=list)       # CoinRow
    stowed_gems: list = Field(default_factory=list)        # GemRow
    stowed_jewellery: list = Field(default_factory=list)   # JewelleryRow
    stowed_magic: list = Field(default_factory=list)       # MagicItemView
    stowed_enchanted: list = Field(default_factory=list)   # EnchantedView
    stowed_ammo: list = Field(default_factory=list)        # AmmoRow
    stowed_spell_sources: list = Field(default_factory=list)  # SpellSourceView


class CoinRow(BaseModel):
    denom: str
    count: int


class OwnerCaps(BaseModel):
    """Per-inventory capabilities; templates gate on these (no per-owner branches)."""
    has_equipped: bool = False    # show Equipped subsection + label is "Carried"
    can_wield: bool = False       # inline/modal Equip on loose rows
    can_stash: bool = False       # offer Stash/Unstash
    class_filter_equip: bool = True  # PC filters by class; retainers do not
    bucket_label: str = "Carried"    # "Carried" or "Stowed"


class TopLevelGroup(BaseModel):
    """One inventory pane — Carried, Stashed, or a carrier/retainer."""
    kind: str                             # carried | stashed | animal | vehicle | retainer
    id: str | None = None                 # carrier/retainer instance_id; None for person buckets
    label: str                            # display name
    caps: OwnerCaps = Field(default_factory=OwnerCaps)
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
    magic_items: list = Field(default_factory=list)         # MagicItemView (unequipped)
    enchanted: list = Field(default_factory=list)           # MagicItemView (enchanted)
    spell_sources: list = Field(default_factory=list)       # SpellSourceView
    ammo: list = Field(default_factory=list)                # AmmoView


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


def class_allows(item, allowed_weapons, allowed_armor, allow_shields) -> bool:
    """Whether the character's class may equip ``item`` given the allowance
    sets (or the ``"all"`` sentinel).  Non-equippable items are always True.

    Single source of truth for the *UI* equip-eligibility decision: consumed by
    both the mundane inventory rows (``_build_row``) and the enchanted/magic
    views (``enchanted_items_view``), so the two rendering paths can never
    diverge on what a class may wield.  (``equip()`` in ``equip.py`` is the
    server-side gate that backstops it.)"""
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
        class_allowed=class_allows(item, allowed_weapons, allowed_armor, allow_shields),
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
                   gargantua_1h_2h: bool = False,
                   spec=None) -> InventoryView:
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

    # Build catalog_id → instance_id lookups from spec.items (non-enchanted plain items)
    _iid_carried: dict[str, str] = {}
    _iid_stashed: dict[str, str] = {}
    _iid_equipped: dict[str, str] = {}
    if spec is not None:
        for _i in spec.items:
            if _i.enchantment_id is not None:
                continue
            if _i.location.kind == "carried" and _i.catalog_id not in _iid_carried:
                _iid_carried[_i.catalog_id] = _i.instance_id
            elif _i.location.kind == "stashed" and _i.catalog_id not in _iid_stashed:
                _iid_stashed[_i.catalog_id] = _i.instance_id
            if _i.equip is not None and _i.catalog_id not in _iid_equipped:
                _iid_equipped[_i.catalog_id] = _i.instance_id

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
            r = row(item_id, eq_n)
            eq_rows.append(r.model_copy(update={"instance_id": _iid_equipped.get(item_id, "")}))
        if carried_n:
            r = row(item_id, carried_n)
            carried_rows.append(r.model_copy(update={"instance_id": _iid_carried.get(item_id, "")}))

    stashed_rows = [row(i, n).model_copy(update={"instance_id": _iid_stashed.get(i, "")})
                    for i, n in stash_count.items()]

    container_views: list[ContainerView] = []
    for c in containers:
        if c.location.kind not in ("carried", "stashed"):
            continue   # rendered inside its carrier's card, not the loose list
        catalog = data.items.get(c.catalog_id)
        if not isinstance(catalog, Container):
            continue   # stale catalog id; surface as zero-state
        from aose.engine.storage import items_at, location_load_cn
        cont_loc = StorageLocation(kind="container", id=c.instance_id)
        content_items = items_at(spec, cont_loc) if spec is not None else []
        content_rows = [_build_row(i.catalog_id, i.count, data) for i in content_items]
        content_rows.sort(key=lambda r: r.name)
        raw_used = location_load_cn(spec, cont_loc, data) if spec is not None else 0
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

    # Caller must ensure the container is empty before selling/refunding.

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


def add_free_item(spec, item_id: str, data: GameData) -> None:
    """Add one bundle of ``item_id`` to carried spec.items without spending gold."""
    from aose.engine.equip import is_stackable
    from aose.models import ItemInstance
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    carried = StorageLocation(kind="carried")
    if isinstance(item, Container):
        spec.containers.append(new_container_instance(item_id, data))
        return
    count = _bundle_count(item)
    if is_stackable(item):
        existing = next((i for i in spec.items
                         if i.catalog_id == item_id and i.location == carried
                         and i.enchantment_id is None), None)
        if existing is not None:
            existing.count += count
            return
    spec.items.append(ItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=item_id,
        count=count,
        location=carried,
    ))


def buy_item(spec, item_id: str, data: GameData) -> None:
    """Buy one bundle of ``item_id`` onto carried spec.items, spending carried coins."""
    from aose.engine.equip import is_stackable
    from aose.models import ItemInstance
    if item_id not in data.items:
        raise UnknownItem(f"No item with id {item_id!r}")
    item = data.items[item_id]
    spend(spec, int(item.cost_gp))
    carried = StorageLocation(kind="carried")
    if isinstance(item, Container):
        spec.containers.append(new_container_instance(item_id, data))
        return
    count = _bundle_count(item)
    if is_stackable(item):
        existing = next((i for i in spec.items
                         if i.catalog_id == item_id and i.location == carried
                         and i.enchantment_id is None), None)
        if existing is not None:
            existing.count += count
            return
    spec.items.append(ItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=item_id,
        count=count,
        location=carried,
    ))


def sell_item(spec, item_id: str, mode: str, data: GameData) -> None:
    """Remove one bundle from carried spec.items; credit carried gp per mode."""
    from aose.engine import storage as _storage
    carried = StorageLocation(kind="carried")
    inst = next((i for i in spec.items
                 if i.catalog_id == item_id and i.location == carried
                 and i.enchantment_id is None), None)
    if inst is None:
        raise ValueError(f"{item_id!r} not in carried items")
    item = data.items.get(item_id)
    bundle = _bundle_count(item)
    remove_n = bundle if mode == "refund" else 1
    if inst.count < remove_n:
        raise ValueError(f"Cannot {mode} {item_id!r}: insufficient count {inst.count} < {remove_n}")
    if inst.count <= remove_n:
        inst.equip = None
        inst.loaded_ammo_id = None
        spec.items.remove(inst)
    else:
        inst.count -= remove_n
    credit = _removal_gold(item_id, mode, data)
    if credit:
        _storage._add_coins(spec, "gp", credit, carried)


def sell_container(spec, instance_id: str, mode: str, data: GameData) -> None:
    """Remove a container instance; credit carried gp per mode."""
    from aose.engine import storage as _storage
    from aose.models.storage import StorageLocation as _SL
    if mode in ("sell", "refund"):
        cont_loc = _SL(kind="container", id=instance_id)
        if any(getattr(i, "location", None) == cont_loc for i in (
            spec.items + spec.magic_items + spec.spell_sources +
            list(spec.gems) + list(spec.jewellery)
        )):
            raise ContainerNotEmpty(
                f"Cannot {mode} a container with contents — empty it first"
            )
    src_coll, _ = _storage._find_container_anywhere(spec, instance_id)
    new_containers, credit = remove_container(src_coll, 0, instance_id, mode, data)
    src_coll[:] = new_containers
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))


def sell_from_stash(spec, item_id: str, mode: str, data: GameData) -> None:
    """Remove one bundle from stashed spec.items; credit carried gp per mode."""
    from aose.engine import storage as _storage
    stashed = StorageLocation(kind="stashed")
    inst = next((i for i in spec.items
                 if i.catalog_id == item_id and i.location == stashed
                 and i.enchantment_id is None), None)
    if inst is None:
        raise ValueError(f"{item_id!r} not in stashed items")
    item = data.items.get(item_id)
    bundle = _bundle_count(item)
    remove_n = bundle if mode == "refund" else 1
    if inst.count < remove_n:
        raise ValueError(f"Cannot {mode} {item_id!r}: insufficient count {inst.count} < {remove_n}")
    if inst.count <= remove_n:
        spec.items.remove(inst)
    else:
        inst.count -= remove_n
    credit = _removal_gold(item_id, mode, data)
    if credit:
        _storage._add_coins(spec, "gp", credit, StorageLocation(kind="carried"))
