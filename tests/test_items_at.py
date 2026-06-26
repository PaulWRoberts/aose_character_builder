from pathlib import Path
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


def test_items_at_filters_by_location():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="rope", location=STASHED),
    ])
    assert [i.instance_id for i in storage.items_at(spec, CARRIED)] == ["i1"]
    assert [i.instance_id for i in storage.items_at(spec, STASHED)] == ["i2"]


def test_location_load_counts_item_count_times_weight():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="iron_spike", count=3, location=CARRIED),
    ])
    expected = DATA.items["sword"].weight_cn + 3 * DATA.items["iron_spike"].weight_cn
    assert storage.location_load_cn(spec, CARRIED, DATA) == expected
