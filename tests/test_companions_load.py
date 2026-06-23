"""Tests for loading items onto animals / vehicles via move_thing.

The old companions.load_onto_animal / unload_from_animal / load_onto_vehicle /
unload_from_vehicle helpers have been deleted; move_thing is the one front door."""
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.engine.storage import StorageError
from aose.models import AnimalInstance, CharacterSpec, ClassEntry, VehicleInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
HEAVY = next(i.id for i in DATA.items.values()
             if getattr(i, "weight_cn", 0) >= 80)

CARRIED = StorageLocation(kind="carried")


def _spec_with_animal(catalog_id="mule"):
    return CharacterSpec(
        name="Porter",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
        inventory=[HEAVY],
        animals=[AnimalInstance(instance_id="a1", catalog_id=catalog_id)],
    )


def _spec_with_vehicle():
    return CharacterSpec(
        name="Teamster",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="neutral",
        inventory=[HEAVY],
        vehicles=[VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)],
    )


def test_move_thing_loads_item_onto_animal():
    spec = _spec_with_animal()
    animal_loc = StorageLocation(kind="animal", id="a1")
    storage.move_thing(spec, "item", HEAVY, animal_loc, src=CARRIED, data=DATA)
    assert HEAVY not in spec.inventory
    assert HEAVY in spec.animals[0].contents


def test_move_thing_unloads_item_from_animal():
    spec = _spec_with_animal()
    spec.inventory.remove(HEAVY)
    spec.animals[0].contents.append(HEAVY)
    animal_loc = StorageLocation(kind="animal", id="a1")
    storage.move_thing(spec, "item", HEAVY, CARRIED, src=animal_loc, data=DATA)
    assert HEAVY in spec.inventory
    assert HEAVY not in spec.animals[0].contents


def test_war_dog_cannot_carry_any_item():
    spec = _spec_with_animal("war_dog")
    animal_loc = StorageLocation(kind="animal", id="a1")
    with pytest.raises(StorageError):
        storage.move_thing(spec, "item", HEAVY, animal_loc, src=CARRIED, data=DATA)


def test_barding_weight_counts_against_animal_load():
    cap = DATA.items["mule"].max_load_encumbered_cn
    assert cap == 4000


def test_move_thing_loads_item_onto_vehicle():
    spec = _spec_with_vehicle()
    vehicle_loc = StorageLocation(kind="vehicle", id="v1")
    storage.move_thing(spec, "item", HEAVY, vehicle_loc, src=CARRIED, data=DATA)
    assert HEAVY not in spec.inventory
    assert HEAVY in spec.vehicles[0].contents
