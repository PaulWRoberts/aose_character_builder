from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, ItemInstance
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


def test_partial_move_splits_and_leaves_remainder():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="torch",
                                     count=6, location=CARRIED)])
    storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
    carried = storage.items_at(spec, CARRIED)
    stashed = storage.items_at(spec, STASHED)
    assert carried[0].count == 4
    assert stashed[0].count == 2 and stashed[0].catalog_id == "torch"


def test_partial_move_merges_into_existing_destination_stack():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="torch", count=6, location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="torch", count=1, location=STASHED),
    ])
    storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
    stashed = storage.items_at(spec, STASHED)
    assert len(stashed) == 1 and stashed[0].count == 3      # merged, not fragmented


def test_full_move_of_equippable_repoints_and_clears_equip():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword",
                                     equip="main_hand", location=CARRIED)])
    storage.move_item(spec, "i1", STASHED, data=DATA)
    moved = storage.items_at(spec, STASHED)[0]
    assert moved.equip is None                              # left carried → unequipped


def test_equippable_count_cannot_exceed_one():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)])
    with pytest.raises(storage.StorageError):
        storage.move_item(spec, "i1", STASHED, count=2, data=DATA)
