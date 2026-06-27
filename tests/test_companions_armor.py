import uuid
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import companions
from aose.models import AnimalInstance, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")


def _item(catalog_id):
    return ItemInstance(instance_id=uuid.uuid4().hex, catalog_id=catalog_id, location=CARRIED)


def test_assign_armor_moves_from_inventory_to_animal():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    items = [_item("horse_barding")]
    items, animals = companions.assign_armor(items, animals, "a1", "horse_barding", DATA)
    assert not any(i.catalog_id == "horse_barding" for i in items)
    assert animals[0].armor_id == "horse_barding"


def test_assign_armor_rejects_unfitting():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse")]
    items = [_item("dog_armour")]
    with pytest.raises(ValueError):
        companions.assign_armor(items, animals, "a1", "dog_armour", DATA)


def test_clear_armor_returns_it_to_inventory():
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse",
                              armor_id="horse_barding")]
    items, animals = companions.clear_armor([], animals, "a1", DATA)
    assert any(i.catalog_id == "horse_barding" for i in items)
    assert animals[0].armor_id is None
