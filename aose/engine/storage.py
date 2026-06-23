"""The single movement vocabulary for the inventory: move loose items,
containers, coins, and treasure between StorageLocations, and convert coins
per-stack. All functions mutate ``spec`` in place (many collections are
touched at once, so the pure-return style of shop.py would be unwieldy).

Imports only models + currency. Nothing imports it back into the magic/feature
DAG, so no cycle risk.
"""
from __future__ import annotations

import uuid

from aose.engine.currency import RATES, CurrencyError, convert_amount
from aose.models import CharacterSpec, CoinStack, GemStack, JewelleryPiece
from aose.models.storage import StorageLocation


class StorageError(ValueError):
    """Movement validation errors (routes map to HTTP 400)."""


def _carrier(spec: CharacterSpec, kind: str, id_: str):
    coll = spec.animals if kind == "animal" else spec.vehicles
    for inst in coll:
        if inst.instance_id == id_:
            return inst
    raise StorageError(f"no {kind} with id {id_!r}")


def _retainer(spec: CharacterSpec, id_: str):
    for r in spec.retainers:
        if r.id == id_:
            return r
    raise StorageError(f"no retainer with id {id_!r}")


def _container(spec: CharacterSpec, id_: str):
    for c in spec.containers:
        if c.instance_id == id_:
            return c
    raise StorageError(f"no container with id {id_!r}")


def containers_collection(spec: CharacterSpec, owner: StorageLocation) -> list:
    """The ContainerInstance list that owns containers *at* ``owner``.

    Retainers keep self-contained storage (``retainer.spec.containers``); every
    other owner shares ``spec.containers`` (each entry's own ``location`` selects
    the bucket)."""
    if owner.kind == "retainer":
        return _retainer(spec, owner.id).spec.containers
    return spec.containers


def loose_list(spec: CharacterSpec, loc: StorageLocation) -> list[str]:
    """Return the actual ``list[str]`` that holds loose item ids at ``loc``."""
    if loc.kind == "carried":
        return spec.inventory
    if loc.kind == "stashed":
        return spec.stashed
    if loc.kind == "container":
        return _container(spec, loc.id).contents
    if loc.kind in ("animal", "vehicle"):
        return _carrier(spec, loc.kind, loc.id).contents
    if loc.kind == "retainer":
        return _retainer(spec, loc.id).spec.inventory
    raise StorageError(f"no loose list for location {loc!r}")


def location_load_cn(spec: CharacterSpec, loc: StorageLocation, data) -> int:
    """Raw encumbrance weight of every substrate stored *at* ``loc``.

    Loose items by ``weight_cn``; coins 1 cn each; gems 1 cn each; jewellery
    10 cn each; ammunition 0 cn; magic items by treasure-weight-or-own-weight;
    enchanted by resolved weight; scroll spell sources 1 cn (spellbooks 0).
    Does NOT include an animal's worn barding (that is added by the capacity
    check). This is the single definition of "current load here", shared with
    the encumbrance container loop.
    """
    from aose.engine.encumbrance import treasure_item_weight
    from aose.engine.enchant import resolve_instance
    from aose.models import Armor, Weapon

    try:
        loose = loose_list(spec, loc)
    except StorageError:
        loose = []
    total = 0
    for item_id in loose:
        item = data.items.get(item_id)
        if item is not None:
            total += item.weight_cn
    total += sum(s.count for s in spec.coins if s.location == loc)
    total += sum(g.count for g in spec.gems if g.location == loc)
    total += 10 * sum(1 for j in spec.jewellery if j.location == loc)
    for mi in spec.magic_items:
        if mi.location == loc:
            item = data.items.get(mi.catalog_id)
            if item is not None:
                total += treasure_item_weight(item) or item.weight_cn
    for inst in spec.enchanted:
        if inst.location == loc:
            resolved = resolve_instance(inst, data)
            if isinstance(resolved, Armor):
                total += int(resolved.weight_cn * resolved.weight_multiplier)
            elif isinstance(resolved, Weapon):
                total += resolved.weight_cn
    total += sum(1 for s in spec.spell_sources
                 if s.location == loc and s.kind == "scroll")
    return total


def _check_capacity(spec: CharacterSpec, dest: StorageLocation,
                    added_cn: int, data) -> None:
    """Reject a move that would push a capacity-bound destination over its cap.

    Hard caps: container (capacity_cn), animal (max_load_encumbered_cn, incl.
    worn barding), vehicle (cargo_capacity_cn). carried / stashed / retainer have
    no hard cap (PC + retainer suffer encumbrance instead; stashed is weightless).
    A ``None`` cap means unlimited — except an animal that is not a beast of
    burden (cap None) carries nothing, so any positive load is rejected.
    """
    if dest.kind in ("carried", "stashed", "retainer"):
        return
    if dest.kind == "container":
        catalog = data.items.get(_container(spec, dest.id).catalog_id)
        cap = getattr(catalog, "capacity_cn", None)
        current = location_load_cn(spec, dest, data)
        if cap is not None and current + added_cn > cap:
            raise StorageError(
                f"{getattr(catalog, 'name', dest.id)} full: "
                f"{current}/{cap} cn, move adds {added_cn} cn")
        return
    if dest.kind == "animal":
        from aose.engine.companions import animal_capacity
        animal = _carrier(spec, "animal", dest.id)
        cap = animal_capacity(animal, data)   # max_load_encumbered_cn or None
        worn = (data.items[animal.armor_id].weight_cn
                if animal.armor_id and animal.armor_id in data.items else 0)
        current = worn + location_load_cn(spec, dest, data)
        if cap is None or current + added_cn > cap:
            name = data.items[animal.catalog_id].name if animal.catalog_id in data.items else dest.id
            raise StorageError(f"{name} cannot carry that much "
                               f"({current}/{cap if cap is not None else 0} cn)")
        return
    if dest.kind == "vehicle":
        from aose.engine.companions import vehicle_capacity
        vehicle = _carrier(spec, "vehicle", dest.id)
        cap = vehicle_capacity(vehicle, data)
        current = location_load_cn(spec, dest, data)
        if current + added_cn > cap:
            name = data.items[vehicle.catalog_id].name if vehicle.catalog_id in data.items else dest.id
            raise StorageError(f"{name} is over capacity ({current}/{cap} cn)")
        return
    raise StorageError(f"no capacity rule for destination {dest.kind!r}")


def use_as_container(spec: CharacterSpec, owner: StorageLocation,
                     item_id: str, data) -> None:
    """Promote one loose copy of a Container item at ``owner`` into a real
    ContainerInstance at that owner. No nesting (owner may not be a container)."""
    from aose.engine.shop import new_container_instance
    from aose.models import Container
    if owner.kind == "container":
        raise StorageError("take the item out of the container first")
    item = data.items.get(item_id)
    if not isinstance(item, Container):
        raise StorageError(f"{item_id!r} is not a container")
    loose = loose_list(spec, owner)
    if item_id not in loose:
        raise StorageError(f"{item_id!r} not at {owner.kind}")
    coll = containers_collection(spec, owner)
    loc = StorageLocation(kind="carried") if owner.kind == "retainer" else owner
    loose.remove(item_id)
    coll.append(new_container_instance(item_id, data, location=loc))


def move_item(spec: CharacterSpec, item_id: str,
              src: StorageLocation, dest: StorageLocation,
              data=None) -> None:
    """Move one copy of ``item_id`` from ``src``'s loose list to ``dest``'s.
    If the moved copy was the last carried copy occupying an equipped slot,
    free that slot (and unload any ammo keyed to it)."""
    src_list = loose_list(spec, src)
    if item_id not in src_list:
        raise StorageError(f"{item_id!r} not at {src.kind}")
    dest_list = loose_list(spec, dest)
    if data is not None:
        item = data.items.get(item_id)
        added = item.weight_cn if item is not None else 0
        _check_capacity(spec, dest, added, data)
    src_list.remove(item_id)
    dest_list.append(item_id)
    # If no carried copy remains, free any equipped slot pointing at it.
    if src.kind == "carried" and spec.inventory.count(item_id) == 0:
        for slot, iid in list(spec.equipped.items()):
            if iid == item_id:
                del spec.equipped[slot]
                unload_if_loaded(spec, item_id)


def _find_container_anywhere(spec: CharacterSpec, container_id: str):
    """Return (collection_list, index) for a container in spec.containers or any
    retainer.spec.containers."""
    for i, c in enumerate(spec.containers):
        if c.instance_id == container_id:
            return spec.containers, i
    for r in spec.retainers:
        for i, c in enumerate(r.spec.containers):
            if c.instance_id == container_id:
                return r.spec.containers, i
    raise StorageError(f"no container with id {container_id!r}")


def move_container(spec: CharacterSpec, container_id: str,
                   dest: StorageLocation) -> None:
    """Re-home a container. ``dest`` may not be a container (no nesting).
    A retainer dest moves the instance between containers lists; all
    other moves only update the instance ``location``."""
    if dest.kind == "container":
        raise StorageError("a container cannot go inside another container")
    src_coll, idx = _find_container_anywhere(spec, container_id)
    c = src_coll[idx]
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)            # validate existence
    dest_coll = containers_collection(spec, dest)
    new_loc = StorageLocation(kind="carried") if dest.kind == "retainer" else dest
    if dest_coll is src_coll:
        c.location = new_loc
    else:
        src_coll.pop(idx)
        dest_coll.append(c.model_copy(update={"location": new_loc}))


def _find_coin(spec: CharacterSpec, denom: str, loc: StorageLocation) -> CoinStack | None:
    for s in spec.coins:
        if s.denom == denom and s.location == loc:
            return s
    return None


def _add_coins(spec: CharacterSpec, denom: str, count: int, loc: StorageLocation) -> None:
    if count <= 0:
        return
    existing = _find_coin(spec, denom, loc)
    if existing is not None:
        existing.count += count
    else:
        spec.coins.append(CoinStack(denom=denom, count=count, location=loc))


def _take_coins(spec: CharacterSpec, denom: str, count: int, loc: StorageLocation) -> None:
    s = _find_coin(spec, denom, loc)
    if s is None or s.count < count:
        have = s.count if s else 0
        raise StorageError(f"only {have} {denom} at {loc.kind}, need {count}")
    s.count -= count
    if s.count == 0:
        spec.coins.remove(s)


def move_coins(spec: CharacterSpec, denom: str,
               src: StorageLocation, dest: StorageLocation, count: int) -> None:
    if count <= 0:
        raise StorageError("move count must be positive")
    _take_coins(spec, denom, count, src)
    _add_coins(spec, denom, count, dest)


def add_coins(spec: CharacterSpec, denom: str, count: int,
              loc: StorageLocation) -> None:
    """GM grant of coins into a location's stack."""
    if count <= 0:
        raise StorageError("grant count must be positive")
    _add_coins(spec, denom, count, loc)


def convert_coins(spec: CharacterSpec, loc: StorageLocation,
                  frm: str, to: str, count: int) -> None:
    """Convert ``count`` ``frm`` coins into ``to`` coins, in place at ``loc``.
    Raises CurrencyError on a non-whole-coin result (no implicit rounding)."""
    gained = convert_amount(frm, to, count)   # raises CurrencyError
    _take_coins(spec, frm, count, loc)        # raises StorageError if short
    _add_coins(spec, to, gained, loc)


def move_ammo(spec: CharacterSpec, instance_id: str,
              dest: StorageLocation, count: int) -> None:
    """Split ``count`` off the ammo stack and merge it into the matching
    (base_id, enchantment_id, dest) stack. Moving the *entire* stack first
    unloads it from any weapon that has it loaded."""
    from aose.engine import ammo as _ammo
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    src = next((s for s in spec.ammo if s.instance_id == instance_id), None)
    if src is None:
        raise StorageError(f"no ammo stack {instance_id!r}")
    if count <= 0 or count > src.count:
        raise StorageError(f"cannot move {count} of {src.count} ammo")
    if count == src.count:
        for key, iid in list(spec.loaded_ammo.items()):
            if iid == instance_id:
                unload_if_loaded(spec, key)
    # Capture base/enchantment before mutating
    base_id = src.base_id
    enchantment_id = src.enchantment_id
    src.count -= count
    if src.count == 0:
        spec.ammo.remove(src)
    spec.ammo = _ammo._combine(spec.ammo, base_id, enchantment_id,
                               count, location=dest)


def unload_if_loaded(spec: CharacterSpec, weapon_key: str) -> None:
    """Drop any loaded-ammo reference keyed by ``weapon_key`` (no-op if absent).
    Run before a weapon or its full ammo stack leaves its bucket so no weapon
    points at a relocated/merged stack."""
    if weapon_key in spec.loaded_ammo:
        del spec.loaded_ammo[weapon_key]


def move_valuable(spec: CharacterSpec, instance_id: str,
                  dest: StorageLocation, count: int | None = None) -> None:
    """Move a gem stack or jewellery piece (by instance_id) to ``dest``.
    For a gem, ``count`` splits N off the source and merges into the matching
    (value, label, dest) stack; ``count=None`` moves the whole stack.
    Jewellery is per-piece; ``count`` is ignored."""
    if dest.kind == "container":
        _container(spec, dest.id)
    for i, g in enumerate(spec.gems):
        if g.instance_id == instance_id:
            n = g.count if count is None else count
            if n <= 0 or n > g.count:
                raise StorageError(f"cannot move {n} of {g.count} gems")
            target = next((o for o in spec.gems
                           if o is not g and o.value == g.value
                           and o.label == g.label and o.location == dest), None)
            if target is not None:
                target.count += n
            else:
                spec.gems.append(GemStack(instance_id=uuid.uuid4().hex,
                                          value=g.value, count=n, label=g.label,
                                          location=dest))
            g.count -= n
            if g.count == 0:
                spec.gems.remove(g)
            return
    for j in spec.jewellery:
        if j.instance_id == instance_id:
            j.location = dest
            return
    raise StorageError(f"no gem/jewellery with id {instance_id!r}")


def _world_lists(world_spec: CharacterSpec, kind: str) -> list:
    return world_spec.magic_items if kind == "magic" else world_spec.enchanted


def _find_instance(spec: CharacterSpec, kind: str, instance_id: str):
    """Locate a magic/enchanted instance in the PC world or any retainer world.
    Returns (owner_spec, list, inst)."""
    for x in _world_lists(spec, kind):
        if x.instance_id == instance_id:
            return spec, _world_lists(spec, kind), x
    for r in spec.retainers:
        for x in _world_lists(r.spec, kind):
            if x.instance_id == instance_id:
                return r.spec, _world_lists(r.spec, kind), x
    raise StorageError(f"no {kind} instance {instance_id!r}")


def move_instance(spec: CharacterSpec, kind: str, instance_id: str,
                  dest: StorageLocation) -> None:
    """Move a magic or enchanted instance to ``dest`` from anywhere (PC or a
    retainer world). Auto-unequips first (clears the instance ``equipped`` flag
    and any owning-spec equipped slot pointing at it). A move that crosses
    worlds (PC↔retainer) is a list-to-list move; within a world it re-points
    the instance ``location``."""
    if kind not in ("magic", "enchanted"):
        raise StorageError(f"move_instance: bad kind {kind!r}")
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    owner_spec, src_list, inst = _find_instance(spec, kind, instance_id)
    # Auto-unequip on the owning spec.
    catalog_id = getattr(inst, "catalog_id", None) or getattr(inst, "base_id", None)
    inst.equipped = False
    for slot, iid in list(owner_spec.equipped.items()):
        if iid == catalog_id:
            del owner_spec.equipped[slot]
            unload_if_loaded(owner_spec, catalog_id)
    dest_world = _retainer(spec, dest.id).spec if dest.kind == "retainer" else spec
    if dest_world is owner_spec:
        inst.location = dest                       # same world → re-point
    else:
        src_list.remove(inst)                       # cross world → list-to-list
        new_loc = (StorageLocation(kind="carried")
                   if dest.kind == "retainer" else dest)
        _world_lists(dest_world, kind).append(inst.model_copy(update={"location": new_loc}))


def move_thing(spec: CharacterSpec, category: str, ref_id: str,
               dest: StorageLocation, *, count: int | None = None,
               src: StorageLocation | None = None, data=None) -> None:
    """Single movement front door. ``category`` selects the substrate.
    ``count`` applies to coins/gems/ammo; ``src`` is required for loose items
    (which list to pull from). ``data`` is used by item moves' validation."""
    if category == "item":
        if src is None:
            raise StorageError("item move requires src")
        unload_if_loaded(spec, ref_id)            # a loaded weapon unloads first
        move_item(spec, ref_id, src, dest)
    elif category == "container":
        move_container(spec, ref_id, dest)
    elif category == "coin":
        move_coins(spec, ref_id, src or StorageLocation(kind="carried"), dest,
                   count if count is not None else 0)
    elif category in ("gem", "jewellery"):
        move_valuable(spec, ref_id, dest, count=count)
    elif category == "ammo":
        move_ammo(spec, ref_id, dest, count if count is not None else 0)
    elif category in ("magic", "enchanted"):
        move_instance(spec, category, ref_id, dest)
    else:
        raise StorageError(f"unknown move category {category!r}")


def move_targets(spec: CharacterSpec, data) -> list[dict]:
    """Every top-level inventory + every container (PC and retainer) as
    {kind, id, label} dicts, for the shared Move control."""
    out: list[dict] = [
        {"kind": "carried", "id": None, "label": spec.name or "Carried"},
        {"kind": "stashed", "id": None, "label": "Stashed"},
    ]
    for a in spec.animals:
        cat = data.items.get(a.catalog_id)
        out.append({"kind": "animal", "id": a.instance_id,
                    "label": a.name or (cat.name if cat else a.catalog_id)})
    for v in spec.vehicles:
        cat = data.items.get(v.catalog_id)
        out.append({"kind": "vehicle", "id": v.instance_id,
                    "label": v.name or (cat.name if cat else v.catalog_id)})
    for r in spec.retainers:
        out.append({"kind": "retainer", "id": r.id, "label": r.spec.name})
    for c in spec.containers:
        cat = data.items.get(c.catalog_id)
        out.append({"kind": "container", "id": c.instance_id,
                    "label": (cat.name if cat else c.catalog_id)})
    for r in spec.retainers:
        for c in r.spec.containers:
            cat = data.items.get(c.catalog_id)
            out.append({"kind": "container", "id": c.instance_id,
                        "label": f"{r.spec.name} ▸ {cat.name if cat else c.catalog_id}"})
    return out
