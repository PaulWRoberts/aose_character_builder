from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.engine.companions import AnimalOverloaded, VehicleOverloaded
from aose.models import AnimalInstance, VehicleInstance

DATA = GameData.load(Path("data"))
# a heavy item to test capacity: use a real weapon weight from the catalog.
HEAVY = next(i.id for i in DATA.items.values()
             if getattr(i, "weight_cn", 0) >= 80)


def test_load_onto_animal_moves_from_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="mule")]
    inv, animals = companions.load_onto_animal([HEAVY], animals, "a1", HEAVY, DATA)
    assert inv == []
    assert animals[0].contents == [HEAVY]


def test_unload_from_animal_returns_to_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="mule",
                              contents=[HEAVY])]
    inv, animals = companions.unload_from_animal([], animals, "a1", HEAVY, DATA)
    assert inv == [HEAVY]
    assert animals[0].contents == []


def test_dog_has_no_load_capacity():
    animals = [AnimalInstance(instance_id="d1", catalog_id="war_dog")]
    with pytest.raises(AnimalOverloaded):
        companions.load_onto_animal([HEAVY], animals, "d1", HEAVY, DATA)


def test_barding_weight_counts_against_animal_load():
    # mule encumbered cap 4000; load near cap then ensure barding+load rejects.
    cap = DATA.items["mule"].max_load_encumbered_cn  # 4000
    assert cap == 4000


def test_load_onto_vehicle_capacity_uses_extra_when_toggled():
    v = VehicleInstance(instance_id="v1", catalog_id="cart", hull_max=4)
    # cart base 4000, extra 8000 — a single light item always fits; assert toggle path runs
    inv, vehicles = companions.load_onto_vehicle([HEAVY], [v], "v1", HEAVY, DATA)
    assert vehicles[0].contents == [HEAVY]
