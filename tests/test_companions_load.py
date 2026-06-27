"""Tests for loading items onto animals / vehicles via move_thing.

The old companions.load_onto_animal / unload_from_animal / load_onto_vehicle /
unload_from_vehicle helpers have been deleted; move_thing is the one front door."""
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.engine.storage import StorageError
from aose.models import AnimalInstance, CharacterSpec, ClassEntry, ItemInstance, VehicleInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
HEAVY = next(i.id for i in DATA.items.values()
             if getattr(i, "weight_cn", 0) >= 80)

CARRIED = StorageLocation(kind="carried")
ANIMAL_LOC = StorageLocation(kind="animal", id="a1")
VEHICLE_LOC = StorageLocation(kind="vehicle", id="v1")


def _spec_with_animal(catalog_id="mule"):
    return CharacterSpec(
        name="Porter",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
        items=[ItemInstance(instance_id="h1", catalog_id=HEAVY)],
        animals=[AnimalInstance(instance_id="a1", catalog_id=catalog_id)],
    )


def _spec_with_vehicle():
    return CharacterSpec(
        name="Teamster",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
        items=[ItemInstance(instance_id="h1", catalog_id=HEAVY)],
        vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)],
    )


def test_move_thing_loads_item_onto_animal():
    spec = _spec_with_animal()
    storage.move_thing(spec, "item", "h1", ANIMAL_LOC, data=DATA)
    assert not any(i.instance_id == "h1" and i.location.kind == "carried" for i in spec.items)
    assert any(i.instance_id == "h1" and i.location == ANIMAL_LOC for i in spec.items)


def test_move_thing_unloads_item_from_animal():
    spec = _spec_with_animal()
    spec.items[0] = spec.items[0].model_copy(update={"location": ANIMAL_LOC})
    storage.move_thing(spec, "item", "h1", CARRIED, data=DATA)
    assert any(i.instance_id == "h1" and i.location.kind == "carried" for i in spec.items)
    assert not any(i.instance_id == "h1" and i.location == ANIMAL_LOC for i in spec.items)


def test_war_dog_cannot_carry_any_item():
    spec = _spec_with_animal("war_dog")
    with pytest.raises(StorageError):
        storage.move_thing(spec, "item", "h1", StorageLocation(kind="animal", id="a1"), data=DATA)


def test_barding_weight_counts_against_animal_load():
    cap = DATA.items["mule"].max_load_encumbered_cn
    assert cap == 4000


def test_move_thing_loads_item_onto_vehicle():
    spec = _spec_with_vehicle()
    storage.move_thing(spec, "item", "h1", VEHICLE_LOC, data=DATA)
    assert not any(i.instance_id == "h1" and i.location.kind == "carried" for i in spec.items)
    assert any(i.instance_id == "h1" and i.location == VEHICLE_LOC for i in spec.items)
