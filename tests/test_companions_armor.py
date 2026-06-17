from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.models import AnimalInstance

DATA = GameData.load(Path("data"))


def test_assign_armor_moves_from_inventory_to_animal():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    inv = ["horse_barding"]
    inv, animals = companions.assign_armor(inv, animals, "a1", "horse_barding", DATA)
    assert inv == []
    assert animals[0].armor_id == "horse_barding"


def test_assign_armor_rejects_unfitting():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    with pytest.raises(ValueError):
        companions.assign_armor(["dog_armour"], animals, "a1", "dog_armour", DATA)


def test_clear_armor_returns_it_to_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse",
                              armor_id="horse_barding")]
    inv, animals = companions.clear_armor([], animals, "a1", DATA)
    assert inv == ["horse_barding"]
    assert animals[0].armor_id is None
