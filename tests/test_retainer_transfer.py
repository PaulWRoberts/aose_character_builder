from pathlib import Path
import random
import pytest
from aose.data.loader import GameData
from aose.engine import retainers, storage
from aose.models import CharacterSpec, ItemInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _pc_with_retainer():
    pc = CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral",
        items=[ItemInstance(instance_id="torch1", catalog_id="torch")])
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    return pc


def test_transfer_to_retainer_moves_item():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    storage.move_thing(pc, "item", "torch1",
                       StorageLocation(kind="retainer", id=rid), data=DATA)
    assert not any(i.instance_id == "torch1" and i.location.kind == "carried"
                   for i in pc.items)
    assert any(i.catalog_id == "torch" and i.location.kind == "carried"
               for i in pc.retainers[0].spec.items)


def test_transfer_to_pc_moves_item_back():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    ret_torch_iid = "ret_torch1"
    pc.retainers[0].spec.items.append(
        ItemInstance(instance_id=ret_torch_iid, catalog_id="torch"))
    storage.move_thing(pc, "item", ret_torch_iid,
                       StorageLocation(kind="carried"), data=DATA)
    assert any(i.catalog_id == "torch" and i.location.kind == "carried"
               for i in pc.items)


def test_transfer_missing_item_raises():
    pc = _pc_with_retainer()
    with pytest.raises(storage.StorageError):
        storage.move_thing(pc, "item", "no-such-iid",
                           StorageLocation(kind="retainer", id=pc.retainers[0].id),
                           data=DATA)
