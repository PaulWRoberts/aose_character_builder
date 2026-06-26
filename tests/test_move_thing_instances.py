"""Task 8 verification tests: move_thing by instance_id + capacity via policy.
These new-model tests run independently while the legacy test_storage_move_thing.py
file is still broken (Part 5 will migrate that file). In Task 22, these cases
will be consolidated into the migrated file and this file removed."""
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, ContainerInstance, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))
CARRIED = StorageLocation(kind="carried")
STASHED = StorageLocation(kind="stashed")


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_move_thing_item_by_instance_id_into_container():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="torch", count=3, location=CARRIED),
               ItemInstance(instance_id="i2", catalog_id="backpack", location=CARRIED)],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=CARRIED)],
    )
    dest = StorageLocation(kind="container", id="c1")
    storage.move_thing(spec, "item", "i1", dest, count=2, data=DATA)
    inside = storage.items_at(spec, dest)
    assert inside[0].catalog_id == "torch" and inside[0].count == 2


def test_check_capacity_reads_policy_descriptor():
    spec = _spec(
        items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)],
        containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                                      location=CARRIED)],   # cap 50 < sword 60
    )
    dest = StorageLocation(kind="container", id="p1")
    with pytest.raises(storage.StorageError):
        storage.move_thing(spec, "item", "i1", dest, data=DATA)
