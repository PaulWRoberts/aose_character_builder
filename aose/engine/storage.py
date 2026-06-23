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
              src: StorageLocation, dest: StorageLocation) -> None:
    """Move one copy of ``item_id`` from ``src``'s loose list to ``dest``'s."""
    src_list = loose_list(spec, src)
    if item_id not in src_list:
        raise StorageError(f"{item_id!r} not at {src.kind}")
    dest_list = loose_list(spec, dest)
    src_list.remove(item_id)
    dest_list.append(item_id)


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
