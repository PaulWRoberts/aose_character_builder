import uuid
from pathlib import Path
import pytest

from aose.data.loader import GameData
from aose.models import CharacterSpec, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.engine import inventory_actions as ia

DATA = GameData.load(Path(__file__).parent.parent / "data")

ENCHANT_ID = "sword_plus_1"


def _spec(**kw):
    """Minimal-but-valid PC, matching tests/test_equip_core.py::_spec."""
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def _spec_with(catalog_id, enchantment_id=None):
    iid = uuid.uuid4().hex
    spec = _spec(items=[ItemInstance(
        instance_id=iid, catalog_id=catalog_id, count=1,
        location=StorageLocation(kind="carried"), enchantment_id=enchantment_id,
    )])
    return spec, iid


def test_equip_thing_item_sets_slot():
    spec, iid = _spec_with("sword")
    ia.equip_thing(spec, "item", iid, data=DATA, owner=None)
    assert next(i for i in spec.items if i.instance_id == iid).equip == "main_hand"


def test_unequip_thing_item_clears_slot():
    spec, iid = _spec_with("sword")
    ia.equip_thing(spec, "item", iid, data=DATA, owner=None)
    ia.unequip_thing(spec, "item", iid, owner=None)
    assert next(i for i in spec.items if i.instance_id == iid).equip is None


def test_bad_category_raises():
    spec, iid = _spec_with("sword")
    with pytest.raises(ia.InventoryActionError):
        ia.equip_thing(spec, "bogus", iid, data=DATA, owner=None)
