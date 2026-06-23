"""Acquisition + storage-location helpers for owned animals and vehicles.

Mirrors aose/engine/shop.py's container helpers: each buy creates a per-instance
roster entry rather than a flat inventory id, and load/unload move loose gear
between the PC's inventory and a carrier's contents (capacity-checked). The PC's
encumbrance is never affected — carrier contents live in their own lists.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.data.loader import GameData
from aose.engine.dice import roll
from aose.engine.shop import InsufficientGold, REMOVE_MODES, UnknownItem
from aose.models import (
    Animal, AnimalInstance, AnimalArmor, CharacterSpec, Container,
    Vehicle, VehicleInstance,
)


class LoadError(ValueError):
    pass


class AnimalOverloaded(LoadError):
    pass


class VehicleOverloaded(LoadError):
    pass


def _require(data: GameData, item_id: str, kind: type, label: str):
    item = data.items.get(item_id)
    if item is None:
        raise UnknownItem(f"No item with id {item_id!r}")
    if not isinstance(item, kind):
        raise ValueError(f"{item_id!r} is not {label}")
    return item


def resolve_hull_max(hull_points: str, rng: Optional[random.Random] = None) -> int:
    """A dice expression ("1d4") is rolled; a range ("60-80") takes its maximum
    (a sound, newly-built vessel). Editable afterward by the player."""
    s = hull_points.strip()
    if "d" in s:
        return roll(s, rng)
    if "-" in s:
        return int(s.split("-")[-1])
    return int(s)


# ── Animals ────────────────────────────────────────────────────────────────

def buy_animal(animals: list[AnimalInstance], gold: int, catalog_id: str,
               data: GameData) -> tuple[list[AnimalInstance], int]:
    item = _require(data, catalog_id, Animal, "an animal")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand")
    inst = AnimalInstance(instance_id=uuid.uuid4().hex, catalog_id=catalog_id)
    return [*animals, inst], gold - cost


def add_free_animal(animals: list[AnimalInstance], catalog_id: str,
                    data: GameData) -> list[AnimalInstance]:
    _require(data, catalog_id, Animal, "an animal")
    return [*animals, AnimalInstance(instance_id=uuid.uuid4().hex,
                                     catalog_id=catalog_id)]


def remove_animal(animals: list[AnimalInstance], gold: int, instance_id: str,
                  mode: str, data: GameData) -> tuple[list[AnimalInstance], int]:
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}")
    idx = next((i for i, a in enumerate(animals)
                if a.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No animal with id {instance_id!r}")
    catalog = data.items.get(animals[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = cost if mode == "refund" else (cost // 2 if mode == "sell" else 0)
    return [*animals[:idx], *animals[idx + 1:]], gold + refund


# ── Vehicles ───────────────────────────────────────────────────────────────

def buy_vehicle(vehicles: list[VehicleInstance], gold: int, catalog_id: str,
                data: GameData, rng: Optional[random.Random] = None
                ) -> tuple[list[VehicleInstance], int]:
    item = _require(data, catalog_id, Vehicle, "a vehicle")
    cost = int(item.cost_gp)
    if gold < cost:
        raise InsufficientGold(
            f"Cannot afford {item.name}: {cost} gp required, {gold} on hand")
    inst = VehicleInstance(instance_id=uuid.uuid4().hex, catalog_id=catalog_id,
                           hull_max=resolve_hull_max(item.hull_points, rng))
    return [*vehicles, inst], gold - cost


def add_free_vehicle(vehicles: list[VehicleInstance], catalog_id: str,
                     data: GameData, rng: Optional[random.Random] = None
                     ) -> list[VehicleInstance]:
    item = _require(data, catalog_id, Vehicle, "a vehicle")
    return [*vehicles, VehicleInstance(
        instance_id=uuid.uuid4().hex, catalog_id=catalog_id,
        hull_max=resolve_hull_max(item.hull_points, rng))]


def remove_vehicle(vehicles: list[VehicleInstance], gold: int, instance_id: str,
                   mode: str, data: GameData
                   ) -> tuple[list[VehicleInstance], int]:
    if mode not in REMOVE_MODES:
        raise ValueError(f"Unknown remove mode {mode!r}")
    idx = next((i for i, v in enumerate(vehicles)
                if v.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No vehicle with id {instance_id!r}")
    catalog = data.items.get(vehicles[idx].catalog_id)
    cost = int(catalog.cost_gp) if catalog else 0
    refund = cost if mode == "refund" else (cost // 2 if mode == "sell" else 0)
    return [*vehicles[:idx], *vehicles[idx + 1:]], gold + refund


# ── Armour ─────────────────────────────────────────────────────────────────

def _find_animal(animals, instance_id):
    idx = next((i for i, a in enumerate(animals)
                if a.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No animal with id {instance_id!r}")
    return idx


def assign_armor(inventory: list[str], animals: list[AnimalInstance],
                 instance_id: str, armor_id: str, data: GameData
                 ) -> tuple[list[str], list[AnimalInstance]]:
    """Move an AnimalArmor from inventory onto the animal. Validates fit."""
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    armor = _require(data, armor_id, AnimalArmor, "animal armour")
    catalog = data.items[animal.catalog_id]
    if armor_id not in catalog.armor_fits:
        raise ValueError(f"{armor.name} does not fit {catalog.name}")
    if armor_id not in inventory:
        raise ValueError(f"{armor_id!r} is not in inventory")
    new_inv = list(inventory)
    new_inv.remove(armor_id)
    # return any previously worn armour to inventory first
    if animal.armor_id:
        new_inv.append(animal.armor_id)
    updated = animal.model_copy(update={"armor_id": armor_id})
    return new_inv, [*animals[:idx], updated, *animals[idx + 1:]]


def clear_armor(inventory: list[str], animals: list[AnimalInstance],
                instance_id: str, data: GameData
                ) -> tuple[list[str], list[AnimalInstance]]:
    idx = _find_animal(animals, instance_id)
    animal = animals[idx]
    new_inv = list(inventory)
    if animal.armor_id:
        new_inv.append(animal.armor_id)
    updated = animal.model_copy(update={"armor_id": None})
    return new_inv, [*animals[:idx], updated, *animals[idx + 1:]]


# ── Load / unload ──────────────────────────────────────────────────────────

def _items_weight(item_ids: list[str], data: GameData) -> int:
    return sum((data.items[i].weight_cn if i in data.items else 0)
               for i in item_ids)


def animal_capacity(animal: AnimalInstance, data: GameData) -> int | None:
    """Encumbered max-load cap (the hard ceiling). None when the animal is not
    a beast of burden (dogs) — meaning it carries nothing."""
    catalog = data.items[animal.catalog_id]
    return catalog.max_load_encumbered_cn


def animal_load_cn(animal: AnimalInstance, data: GameData) -> int:
    """Worn barding weight + loaded contents weight."""
    worn = data.items[animal.armor_id].weight_cn if animal.armor_id else 0
    return worn + _items_weight(animal.contents, data)


def _find_vehicle(vehicles, instance_id):
    idx = next((i for i, v in enumerate(vehicles)
                if v.instance_id == instance_id), None)
    if idx is None:
        raise ValueError(f"No vehicle with id {instance_id!r}")
    return idx


def vehicle_capacity(vehicle: VehicleInstance, data: GameData) -> int:
    catalog = data.items[vehicle.catalog_id]
    if vehicle.extra_animals and catalog.cargo_capacity_extra_cn is not None:
        return catalog.cargo_capacity_extra_cn
    return catalog.cargo_capacity_cn


def vehicle_load_cn(vehicle: VehicleInstance, data: GameData) -> int:
    return _items_weight(vehicle.contents, data)


# ── Container-on-carrier ───────────────────────────────────────────────────

def _set_container_location(spec: CharacterSpec, container_id: str,
                            new_location) -> None:
    from aose.models.storage import StorageLocation
    for i, c in enumerate(spec.containers):
        if c.instance_id == container_id:
            if not isinstance(new_location, StorageLocation):
                new_location = StorageLocation.model_validate(new_location)
            spec.containers[i] = c.model_copy(update={"location": new_location})
            return
    raise ValueError(f"No container with id {container_id!r}")


def move_container_to_animal(spec: CharacterSpec, container_id: str,
                             animal_id: str, data: GameData) -> None:
    from aose.models.storage import StorageLocation
    _find_animal(spec.animals, animal_id)
    _set_container_location(spec, container_id,
                            StorageLocation(kind="animal", id=animal_id))


def move_container_to_vehicle(spec: CharacterSpec, container_id: str,
                              vehicle_id: str, data: GameData) -> None:
    from aose.models.storage import StorageLocation
    _find_vehicle(spec.vehicles, vehicle_id)
    _set_container_location(spec, container_id,
                            StorageLocation(kind="vehicle", id=vehicle_id))


def move_container_to_person(spec: CharacterSpec, container_id: str) -> None:
    from aose.models.storage import StorageLocation
    _set_container_location(spec, container_id, StorageLocation(kind="carried"))
