from pathlib import Path
import pytest
from aose.data.loader import GameData
from aose.engine import storage
from aose.engine.equip import is_equippable, is_stackable
from aose.models import CharacterSpec, ClassEntry, AnimalInstance, ContainerInstance, Retainer
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw); return CharacterSpec(**base)


def test_classification():
    assert is_equippable(DATA.items["sword"]) and not is_stackable(DATA.items["sword"])
    assert is_stackable(DATA.items["torch"]) and not is_equippable(DATA.items["torch"])


def test_person_buckets_uncapped_and_carried_equips():
    spec = _spec()
    carried = storage.location_policy(spec, StorageLocation(kind="carried"), DATA)
    stashed = storage.location_policy(spec, StorageLocation(kind="stashed"), DATA)
    assert carried.capacity_cn is None and carried.equip_allowed is True
    assert stashed.equip_allowed is False


def test_container_capacity_from_catalog():
    spec = _spec(containers=[ContainerInstance(instance_id="p1", catalog_id="belt_pouch",
                            location=StorageLocation(kind="carried"))])
    pol = storage.location_policy(spec, StorageLocation(kind="container", id="p1"), DATA)
    assert pol.capacity_cn == DATA.items["belt_pouch"].capacity_cn
    assert pol.equip_allowed is False


def test_retainer_carried_equips_with_own_eligibility():
    ret = _spec(name="NPC")
    spec = _spec(retainers=[Retainer(id="r1", spec=ret, loyalty=7)])
    pol = storage.location_policy(spec, StorageLocation(kind="retainer", id="r1"), DATA)
    assert pol.equip_allowed is True            # retainer carried bucket
