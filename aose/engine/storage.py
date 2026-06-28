"""The single movement vocabulary for the inventory: move items, containers,
coins, and treasure between StorageLocations, and convert coins per-stack.
All functions mutate ``spec`` in place.

Items are now ``ItemInstance`` objects in the flat ``spec.items`` list; each
carries its own ``location``.  ``move_item`` is instance-based (by
``instance_id``), stacks merge automatically.  Ammo and enchanted gear are
plain ``ItemInstance``s — move them the same way.  ``MagicItemInstance`` still
uses ``move_instance``.  Coins/gems/jewellery/containers/spell-sources keep
their own helper functions.

Imports only models + currency. Nothing imports it back into the magic/feature
DAG, so no cycle risk.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel

from aose.engine.currency import CurrencyError, convert_amount
from aose.models import CharacterSpec, CoinStack, GemStack, ItemInstance, JewelleryPiece
from aose.models.storage import StorageLocation


class StorageError(ValueError):
    """Movement validation errors (routes map to HTTP 400)."""


# ---------------------------------------------------------------------------
# Location policy descriptor
# ---------------------------------------------------------------------------

class LocationPolicy(BaseModel):
    """Uniform per-location policy descriptor. Differences between location
    kinds are these parameters, never code branches: capacity, equip-allowed,
    and the class-eligibility source for equipping here."""
    model_config = {"arbitrary_types_allowed": True}
    capacity_cn: int | None = None       # hard cap; None = uncapped
    equip_allowed: bool = False          # may instances here be equipped
    equips_on_spec: object = None        # the spec whose class gates eligibility


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _container_owner(spec: CharacterSpec, id_: str):
    """Return (owning_spec, ContainerInstance) for a container in the PC world or
    any retainer world. Container contents live in their owner's world."""
    for c in spec.containers:
        if c.instance_id == id_:
            return spec, c
    for r in spec.retainers:
        for c in r.spec.containers:
            if c.instance_id == id_:
                return r.spec, c
    raise StorageError(f"no container with id {id_!r}")


def _container(spec: CharacterSpec, id_: str):
    """The ContainerInstance for ``id_`` in any world (back-compat shim)."""
    return _container_owner(spec, id_)[1]


def _owning_spec_for(spec: CharacterSpec, loc: StorageLocation) -> CharacterSpec:
    """The spec whose world ``loc`` belongs to (PC, or a retainer's spec)."""
    if loc.kind == "retainer":
        return _retainer(spec, loc.id).spec
    if loc.kind == "container":
        return _container_owner(spec, loc.id)[0]
    return spec


def containers_collection(spec: CharacterSpec, owner: StorageLocation) -> list:
    """The ContainerInstance list that owns containers *at* ``owner``.

    Retainers keep self-contained storage (``retainer.spec.containers``); every
    other owner shares ``spec.containers`` (each entry's own ``location`` selects
    the bucket)."""
    if owner.kind == "retainer":
        return _retainer(spec, owner.id).spec.containers
    return spec.containers


# ---------------------------------------------------------------------------
# Location policy
# ---------------------------------------------------------------------------

def location_policy(spec: CharacterSpec, loc: StorageLocation, data) -> LocationPolicy:
    """Return the uniform policy descriptor for ``loc``."""
    if loc.kind == "carried":
        return LocationPolicy(capacity_cn=None, equip_allowed=True, equips_on_spec=spec)
    if loc.kind == "retainer":
        return LocationPolicy(capacity_cn=None, equip_allowed=True,
                              equips_on_spec=_retainer(spec, loc.id).spec)
    if loc.kind == "stashed":
        return LocationPolicy(capacity_cn=None, equip_allowed=False)
    if loc.kind == "container":
        cat = data.items.get(_container(spec, loc.id).catalog_id) if data else None
        return LocationPolicy(capacity_cn=getattr(cat, "capacity_cn", None),
                              equip_allowed=False)
    if loc.kind == "animal":
        from aose.engine.companions import animal_capacity
        animal = _carrier(spec, "animal", loc.id)
        cap = animal_capacity(animal, data) if data else None
        return LocationPolicy(capacity_cn=cap, equip_allowed=False)
    if loc.kind == "vehicle":
        from aose.engine.companions import vehicle_capacity
        cap = vehicle_capacity(_carrier(spec, "vehicle", loc.id), data) if data else None
        return LocationPolicy(capacity_cn=cap, equip_allowed=False)
    return LocationPolicy()


# ---------------------------------------------------------------------------
# Items-by-location
# ---------------------------------------------------------------------------

def items_at(spec: CharacterSpec, loc: StorageLocation) -> list:
    """Every ItemInstance located exactly at ``loc`` in ``spec.items``.
    The caller is responsible for passing the right spec (e.g. for retainer
    items, pass ``retainer.spec`` with ``StorageLocation(kind='carried')``)."""
    return [i for i in spec.items if i.location == loc]


# ---------------------------------------------------------------------------
# Encumbrance at a location
# ---------------------------------------------------------------------------

def location_load_cn(spec: CharacterSpec, loc: StorageLocation, data) -> int:
    """Raw encumbrance weight of everything stored *at* ``loc``.

    Items (plain or enchanted) by ``weight_cn * count``; coins 1 cn each;
    gems 1 cn each; jewellery 10 cn each; magic items by
    treasure-weight-or-own-weight; scroll spell sources 1 cn (spellbooks 0).
    Does NOT include an animal's worn barding. For retainer locations, uses the
    retainer's carried bucket (coins, gems, etc. from the retainer's own spec).
    """
    from aose.engine.encumbrance import treasure_item_weight

    if loc.kind == "retainer":
        owner = _retainer(spec, loc.id).spec
        inner_loc = StorageLocation(kind="carried")
    elif loc.kind == "container":
        owner = _container_owner(spec, loc.id)[0]   # contents live in the owner's world
        inner_loc = loc
    else:
        owner = spec
        inner_loc = loc

    total = 0
    for inst in owner.items:
        if inst.location != inner_loc:
            continue
        item = data.items.get(inst.catalog_id)
        if item is not None:
            total += item.weight_cn * inst.count

    total += sum(s.count for s in owner.coins if s.location == inner_loc)
    total += sum(g.count for g in owner.gems if g.location == inner_loc)
    total += 10 * sum(1 for j in owner.jewellery if j.location == inner_loc)
    for mi in owner.magic_items:
        if mi.location == inner_loc:
            item = data.items.get(mi.catalog_id)
            if item is not None:
                total += treasure_item_weight(item) or item.weight_cn
    total += sum(1 for s in owner.spell_sources
                 if s.location == inner_loc and s.kind == "scroll")
    return total


# ---------------------------------------------------------------------------
# Capacity check (reads policy descriptor)
# ---------------------------------------------------------------------------

def _check_capacity(spec: CharacterSpec, dest: StorageLocation,
                    added_cn: int, data) -> None:
    """Reject a move that would push a capacity-bound destination over its cap."""
    if data is None:
        return
    pol = location_policy(spec, dest, data)
    if pol.capacity_cn is None:
        # Uncapped — but a non-beast-of-burden animal has cap None AND carries
        # nothing; any positive load is still rejected.
        if dest.kind == "animal":
            from aose.engine.companions import animal_capacity
            if animal_capacity(_carrier(spec, "animal", dest.id), data) is None and added_cn > 0:
                raise StorageError("this animal cannot carry cargo")
        return
    worn = 0
    if dest.kind == "animal":
        a = _carrier(spec, "animal", dest.id)
        worn = data.items[a.armor_id].weight_cn if a.armor_id in data.items else 0
    current = worn + location_load_cn(spec, dest, data)
    if current + added_cn > pol.capacity_cn:
        raise StorageError(f"destination full: {current}/{pol.capacity_cn} cn, "
                           f"move adds {added_cn} cn")


# ---------------------------------------------------------------------------
# use_as_container (promotes a loose Container item to a ContainerInstance)
# ---------------------------------------------------------------------------

def use_as_container(spec: CharacterSpec, owner: StorageLocation,
                     item_id: str, data) -> None:
    """Promote one ItemInstance of a Container item at ``owner`` into a real
    ContainerInstance at that owner. No nesting (owner may not be a container)."""
    from aose.engine.shop import new_container_instance
    from aose.models import Container
    if owner.kind == "container":
        raise StorageError("take the item out of the container first")
    item = data.items.get(item_id)
    if not isinstance(item, Container):
        raise StorageError(f"{item_id!r} is not a container")
    if owner.kind == "retainer":
        owner_spec = _retainer(spec, owner.id).spec
        search_loc = StorageLocation(kind="carried")
    else:
        owner_spec = spec
        search_loc = owner
    found = next((i for i in owner_spec.items
                  if i.catalog_id == item_id and i.location == search_loc), None)
    if found is None:
        raise StorageError(f"{item_id!r} not at {owner.kind}")
    coll = containers_collection(spec, owner)
    loc = StorageLocation(kind="carried") if owner.kind == "retainer" else owner
    owner_spec.items.remove(found)
    coll.append(new_container_instance(item_id, data, location=loc))


# ---------------------------------------------------------------------------
# Instance-based item movement
# ---------------------------------------------------------------------------

def _merge_target(spec: CharacterSpec, proto, dest: StorageLocation):
    """Resident stackable ItemInstance at ``dest`` matching proto's merge-key
    ``(catalog_id, enchantment_id)``, or None. Enchantment_id in the key keeps
    +1 arrows from fusing with plain arrows."""
    for i in spec.items:
        if (i.catalog_id == proto.catalog_id
                and i.enchantment_id == proto.enchantment_id
                and i.location == dest):
            return i
    return None


def _clear_equip_state(inst) -> None:
    inst.equip = None
    inst.loaded_ammo_id = None


def _clear_weapon_loads(spec, ammo_iid: str) -> None:
    """Clear loaded_ammo_id on any weapon whose ammo instance was removed/moved away."""
    for i in spec.items:
        if i.loaded_ammo_id == ammo_iid:
            i.loaded_ammo_id = None


def _find_world_list(pc: CharacterSpec, inst) -> list:
    for r in pc.retainers:
        if inst in r.spec.items:
            return r.spec.items
    return pc.items


def _move_cross_world(pc: CharacterSpec, dest_spec: CharacterSpec, inst,
                      dest: StorageLocation, count, data, item=None) -> None:
    """Move an item between two worlds (PC↔retainer). Lands at ``dest`` in the
    destination world (``dest`` is ``carried`` for a retainer target, or the
    container location for a retainer-owned container) and merges into a resident
    stack there."""
    from aose.engine.equip import is_equippable
    if item is None and data is not None:
        item = data.items.get(inst.catalog_id)
    n = inst.count if count is None else count
    equippable = item is not None and is_equippable(item)
    land = StorageLocation(kind="carried") if dest.kind == "retainer" else dest
    src_list = _find_world_list(pc, inst)
    if equippable or n >= inst.count:
        src_list.remove(inst)
        _clear_equip_state(inst)
        resident = None if equippable else _merge_target(dest_spec, inst, land)
        if resident is not None:
            resident.count += n
        else:
            dest_spec.items.append(inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n,
                "location": land, "equip": None, "loaded_ammo_id": None}))
    else:
        inst.count -= n
        resident = _merge_target(dest_spec, inst, land)
        if resident is not None:
            resident.count += n
        else:
            dest_spec.items.append(inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n,
                "location": land, "equip": None, "loaded_ammo_id": None}))


def move_item(spec: CharacterSpec, instance_id: str, dest: StorageLocation,
              *, count: int | None = None, data=None) -> None:
    """Move an ItemInstance (whole, or ``count`` split off a stack) to ``dest``.
    Stackables merge into a resident stack at ``dest`` (one stack per
    catalog+enchantment+location). Equippables re-point whole and clear equip/
    loaded state when they leave ``carried``. Cross-world (PC↔retainer) is a
    list-to-list move landing carried in the destination world."""
    from aose.engine.equip import is_equippable
    src_inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if src_inst is None:
        for r in spec.retainers:
            cand = next((i for i in r.spec.items if i.instance_id == instance_id), None)
            if cand is not None:
                if data is not None:
                    item = data.items.get(cand.catalog_id)
                    n = cand.count if count is None else count
                    added = (item.weight_cn * n) if item is not None else 0
                    _check_capacity(spec, dest, added, data)
                dest_spec = _owning_spec_for(spec, dest)
                _move_cross_world(spec, dest_spec, cand, dest, count, data)
                return
        raise StorageError(f"no item instance {instance_id!r}")

    item = data.items.get(src_inst.catalog_id) if data else None
    n = src_inst.count if count is None else count
    if n <= 0 or n > src_inst.count:
        raise StorageError(f"cannot move {n} of {src_inst.count}")
    equippable = item is not None and is_equippable(item)
    if equippable and n != 1:
        raise StorageError("equippable items are per-instance (count 1)")

    if data is not None:
        added = (item.weight_cn * n) if item is not None else 0
        _check_capacity(spec, dest, added, data)

    dest_spec = _owning_spec_for(spec, dest)
    if dest_spec is not spec:
        _move_cross_world(spec, dest_spec, src_inst, dest, count, data, item=item)
        return

    # Same world. Stackable partial → split/merge; else re-point whole.
    if not equippable and n < src_inst.count:
        src_inst.count -= n
        resident = _merge_target(spec, src_inst, dest)
        if resident is not None:
            resident.count += n
        else:
            spec.items.append(src_inst.model_copy(update={
                "instance_id": uuid.uuid4().hex, "count": n, "location": dest,
                "equip": None, "loaded_ammo_id": None}))
        return
    # Whole move
    resident = None if equippable else _merge_target(spec, src_inst, dest)
    if resident is not None:
        resident.count += src_inst.count
        spec.items.remove(src_inst)
        _clear_weapon_loads(spec, src_inst.instance_id)
    else:
        if dest.kind != "carried":
            _clear_equip_state(src_inst)
            _clear_weapon_loads(spec, src_inst.instance_id)
        src_inst.location = dest


# ---------------------------------------------------------------------------
# Item add (the single stackable-aware add front door)
# ---------------------------------------------------------------------------

def add_item(spec: CharacterSpec, catalog_id: str, count: int,
             loc: StorageLocation, data) -> None:
    """Add ``count`` of ``catalog_id`` at ``loc``. Stackables merge into a
    resident (catalog_id, enchantment_id=None, location) stack; equippables are
    appended as distinct count-1 instances. The single add front door — buy/grant/
    kit paths compose this so merge behaviour can never diverge again."""
    from aose.engine.equip import is_stackable
    item = data.items.get(catalog_id)
    if is_stackable(item):
        resident = next((i for i in spec.items
                         if i.catalog_id == catalog_id and i.enchantment_id is None
                         and i.location == loc), None)
        if resident is not None:
            resident.count += count
            return
        spec.items.append(ItemInstance(instance_id=uuid.uuid4().hex,
                                        catalog_id=catalog_id, count=count,
                                        location=loc))
        return
    for _ in range(count):
        spec.items.append(ItemInstance(instance_id=uuid.uuid4().hex,
                                       catalog_id=catalog_id, count=1, location=loc))


# ---------------------------------------------------------------------------
# Container movement
# ---------------------------------------------------------------------------

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
                   dest: StorageLocation, data=None) -> None:
    """Re-home a container. ``dest`` may not be a container (no nesting).
    A retainer dest moves the instance between containers lists; all
    other moves only update the instance ``location``."""
    if dest.kind == "container":
        raise StorageError("a container cannot go inside another container")
    src_coll, idx = _find_container_anywhere(spec, container_id)
    c = src_coll[idx]
    if dest.kind in ("animal", "vehicle") and data is not None:
        _carrier(spec, dest.kind, dest.id)            # validate existence
    cat = data.items.get(c.catalog_id) if data is not None else None
    added = cat.weight_cn if cat is not None else 0
    _check_capacity(spec, dest, added, data)
    dest_coll = containers_collection(spec, dest)
    new_loc = StorageLocation(kind="carried") if dest.kind == "retainer" else dest
    if dest_coll is src_coll:
        c.location = new_loc
    else:
        src_coll.pop(idx)
        dest_coll.append(c.model_copy(update={"location": new_loc}))


# ---------------------------------------------------------------------------
# Coin movement
# ---------------------------------------------------------------------------

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
               src: StorageLocation, dest: StorageLocation, count: int,
               data=None) -> None:
    if count <= 0:
        raise StorageError("move count must be positive")
    _check_capacity(spec, dest, count, data)
    _take_coins(spec, denom, count, src)
    _add_coins(_owning_spec_for(spec, dest), denom, count, dest)


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


# ---------------------------------------------------------------------------
# Gem / jewellery movement
# ---------------------------------------------------------------------------

def move_valuable(spec: CharacterSpec, instance_id: str,
                  dest: StorageLocation, count: int | None = None,
                  data=None) -> None:
    """Move a gem stack or jewellery piece (by instance_id) to ``dest``.
    For a gem, ``count`` splits N off the source and merges into the matching
    (value, label, dest) stack; ``count=None`` moves the whole stack.
    Jewellery is per-piece; ``count`` is ignored."""
    if dest.kind == "container":
        _container(spec, dest.id)
    owner = _owning_spec_for(spec, dest)
    for g in spec.gems:
        if g.instance_id == instance_id:
            n = g.count if count is None else count
            if n <= 0 or n > g.count:
                raise StorageError(f"cannot move {n} of {g.count} gems")
            _check_capacity(spec, dest, n, data)
            target = next((o for o in owner.gems
                           if o is not g and o.value == g.value
                           and o.label == g.label and o.location == dest), None)
            if target is not None:
                target.count += n
            else:
                owner.gems.append(GemStack(instance_id=uuid.uuid4().hex,
                                           value=g.value, count=n, label=g.label,
                                           location=dest))
            g.count -= n
            if g.count == 0:
                spec.gems.remove(g)
            return
    for j in spec.jewellery:
        if j.instance_id == instance_id:
            _check_capacity(spec, dest, 10, data)
            if owner is spec:
                j.location = dest
            else:
                spec.jewellery.remove(j)
                owner.jewellery.append(j.model_copy(update={"location": dest}))
            return
    raise StorageError(f"no gem/jewellery with id {instance_id!r}")


# ---------------------------------------------------------------------------
# MagicItemInstance movement (enchanted weapons/armour are ItemInstances now)
# ---------------------------------------------------------------------------

def _instance_weight(inst, data) -> int:
    from aose.engine.encumbrance import treasure_item_weight
    item = data.items.get(getattr(inst, "catalog_id", None))
    return (treasure_item_weight(item) or item.weight_cn) if item else 0


def _find_magic_instance(spec: CharacterSpec, instance_id: str):
    """Return (owner_spec, list, inst) for a MagicItemInstance in PC or retainer world."""
    for x in spec.magic_items:
        if x.instance_id == instance_id:
            return spec, spec.magic_items, x
    for r in spec.retainers:
        for x in r.spec.magic_items:
            if x.instance_id == instance_id:
                return r.spec, r.spec.magic_items, x
    raise StorageError(f"no magic instance {instance_id!r}")


def move_instance(spec: CharacterSpec, kind: str, instance_id: str,
                  dest: StorageLocation, data=None) -> None:
    """Move a MagicItemInstance to ``dest`` from anywhere (PC or a retainer world).
    Auto-unequips first (clears the instance ``equipped`` bool). A move that
    crosses worlds (PC↔retainer) is a list-to-list move.

    Note: enchanted weapons/armour are now ``ItemInstance``s — move them via
    ``move_item``. Only ``MagicItemInstance`` (catalog magic items with a toggle
    ``equipped`` bool) comes through here."""
    if kind != "magic":
        raise StorageError(f"move_instance: bad kind {kind!r}; enchanted items use move_item")
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    owner_spec, src_list, inst = _find_magic_instance(spec, instance_id)
    if data is not None:
        added = _instance_weight(inst, data)
        _check_capacity(spec, dest, added, data)
    inst.equipped = False
    dest_world = _owning_spec_for(spec, dest)
    if dest_world is owner_spec:
        inst.location = dest
    else:
        src_list.remove(inst)
        new_loc = (StorageLocation(kind="carried")
                   if dest.kind == "retainer" else dest)
        dest_world.magic_items.append(inst.model_copy(update={"location": new_loc}))


# ---------------------------------------------------------------------------
# Spell source movement
# ---------------------------------------------------------------------------

def _find_spell_source(spec: CharacterSpec, instance_id: str):
    """Return (owner_spec, list, src) for a spell source in the PC world or any
    retainer world."""
    for s in spec.spell_sources:
        if s.instance_id == instance_id:
            return spec, spec.spell_sources, s
    for r in spec.retainers:
        for s in r.spec.spell_sources:
            if s.instance_id == instance_id:
                return r.spec, r.spec.spell_sources, s
    raise StorageError(f"no spell source {instance_id!r}")


def move_spell_source(spec: CharacterSpec, instance_id: str,
                      dest: StorageLocation, data) -> None:
    """Move a spell book / scroll to ``dest``. Same world → re-point location;
    cross world (PC↔retainer) → list-to-list into retainer.spec.spell_sources."""
    if dest.kind in ("animal", "vehicle"):
        _carrier(spec, dest.kind, dest.id)
    if dest.kind == "container":
        _container(spec, dest.id)
    owner_spec, src_list, src = _find_spell_source(spec, instance_id)
    added = 1 if src.kind == "scroll" else 0
    _check_capacity(spec, dest, added, data)
    dest_world = _owning_spec_for(spec, dest)
    if dest_world is owner_spec:
        src.location = dest
    else:
        src_list.remove(src)
        new_loc = (StorageLocation(kind="carried")
                   if dest.kind == "retainer" else dest)
        dest_world.spell_sources.append(src.model_copy(update={"location": new_loc}))


# ---------------------------------------------------------------------------
# Front door: move_thing dispatcher
# ---------------------------------------------------------------------------

def move_thing(spec: CharacterSpec, category: str, ref_id: str,
               dest: StorageLocation, *, count: int | None = None,
               src: StorageLocation | None = None, data=None) -> None:
    """Single movement front door. ``category`` selects the substrate.
    ``count`` applies to coins/gems/item-stacks. ``src`` is only needed for
    coins (denom-keyed). Ammo and enchanted gear are ``ItemInstance``s — use
    ``category="item"`` (or the legacy aliases "ammo"/"enchanted")."""
    if category in ("item", "ammo", "enchanted"):
        move_item(spec, ref_id, dest, count=count, data=data)
    elif category == "container":
        move_container(spec, ref_id, dest, data)
    elif category == "coin":
        move_coins(spec, ref_id, src or StorageLocation(kind="carried"), dest,
                   count if count is not None else 0, data)
    elif category in ("gem", "jewellery"):
        move_valuable(spec, ref_id, dest, count=count, data=data)
    elif category == "magic":
        move_instance(spec, category, ref_id, dest, data)
    elif category == "source":
        move_spell_source(spec, ref_id, dest, data)
    else:
        raise StorageError(f"unknown move category {category!r}")


# ---------------------------------------------------------------------------
# Move-target enumeration (for the shared Move control)
# ---------------------------------------------------------------------------

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
