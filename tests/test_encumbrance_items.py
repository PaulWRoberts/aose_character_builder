"""Task 10 verification: encumbrance.py reads from spec.items flat list."""
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import encumbrance
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
    base.update(kw)
    return CharacterSpec(**base)


def test_carried_weapon_weight_counted():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED)])
    sword = DATA.items["sword"]
    assert encumbrance.equipment_weight_cn(spec, DATA) == sword.weight_cn


def test_stashed_item_not_counted():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=STASHED)])
    assert encumbrance.equipment_weight_cn(spec, DATA) == 0


def test_multiple_weapon_instances_each_counted():
    sword = DATA.items["sword"]
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", location=CARRIED),
        ItemInstance(instance_id="i2", catalog_id="sword", location=CARRIED),
    ])
    assert encumbrance.equipment_weight_cn(spec, DATA) == sword.weight_cn * 2


def test_armor_movement_class_uses_equip_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="chain_mail",
                                     equip="armor", location=CARRIED)])
    chain = DATA.items["chain_mail"]
    assert encumbrance.armor_movement_class(spec, DATA) == chain.movement_impact


def test_no_armor_movement_class_none():
    spec = _spec()
    assert encumbrance.armor_movement_class(spec, DATA) == "none"
