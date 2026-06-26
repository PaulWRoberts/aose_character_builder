# tests/test_equip_core.py
from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import equip
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


def test_equip_sets_instance_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword")])
    equip.equip(spec, "i1", data=DATA)
    assert spec.items[0].equip == "main_hand"
    assert equip.equipped_ref(spec, "main_hand") == "sword"


def test_equip_armor_goes_to_armor_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="plate_mail")])
    equip.equip(spec, "i1", data=DATA)
    assert spec.items[0].equip == "armor"


def test_equip_rejects_non_carried_instance():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", location=STASHED)])
    with pytest.raises(ValueError):
        equip.equip(spec, "i1", data=DATA)


def test_equip_into_occupied_slot_replaces_previous():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand"),
        ItemInstance(instance_id="i2", catalog_id="mace"),
    ])
    equip.equip(spec, "i2", data=DATA)
    assert spec.items[0].equip is None       # displaced
    assert spec.items[1].equip == "main_hand"


def test_unequip_clears_slot():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    equip.unequip(spec, "i1")
    assert spec.items[0].equip is None


def test_two_daggers_dual_wield_are_two_instances():
    spec = _spec(items=[
        ItemInstance(instance_id="i1", catalog_id="dagger"),
        ItemInstance(instance_id="i2", catalog_id="dagger"),
    ], ruleset={"two_weapon_fighting": True})
    equip.equip(spec, "i1", data=DATA)
    equip.equip(spec, "i2", slot="off_hand", data=DATA, two_weapon=True, eligible=True)
    assert equip.equipped_ref(spec, "main_hand") == "dagger"
    assert equip.equipped_ref(spec, "off_hand") == "dagger"


def test_slot_item_resolves_weapon():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    from aose.models import Weapon
    assert isinstance(equip.slot_item(spec, "main_hand", DATA), Weapon)
