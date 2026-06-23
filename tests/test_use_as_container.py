"""Tests for use_as_container: promote a loose Container id into a ContainerInstance."""
from pathlib import Path

import pytest
from aose.data.loader import GameData
from aose.engine.storage import use_as_container, StorageError
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))

_CLS = [{"class_id": "fighter", "level": 1}]
_ABILITIES = {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}


def _pc():
    from aose.models import CharacterSpec
    return CharacterSpec(name="P", abilities=_ABILITIES,
                         race_id="human", classes=_CLS, alignment="neutral")


def test_promotes_carried_backpack():
    spec = _pc(); spec.inventory.append("backpack")
    use_as_container(spec, StorageLocation(kind="carried"), "backpack", DATA)
    assert "backpack" not in spec.inventory
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "backpack"
    assert spec.containers[0].location == StorageLocation(kind="carried")


def test_promotes_stashed_backpack_keeps_location():
    spec = _pc(); spec.stashed.append("backpack")
    use_as_container(spec, StorageLocation(kind="stashed"), "backpack", DATA)
    assert spec.containers[0].location == StorageLocation(kind="stashed")


def test_rejects_non_container():
    spec = _pc(); spec.inventory.append("torch")
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="carried"), "torch", DATA)


def test_rejects_missing_item():
    spec = _pc()
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="carried"), "backpack", DATA)


def test_rejects_promotion_inside_container():
    spec = _pc()
    with pytest.raises(StorageError):
        use_as_container(spec, StorageLocation(kind="container", id="x"),
                         "backpack", DATA)


def test_promotes_onto_retainer_spec():
    from aose.models import Retainer, CharacterSpec
    spec = _pc()
    npc = CharacterSpec(name="H", abilities=_ABILITIES,
                        race_id="human", classes=_CLS, alignment="neutral")
    npc.inventory.append("backpack")
    spec.retainers.append(Retainer(id="r1", spec=npc, loyalty=7, role=""))
    use_as_container(spec, StorageLocation(kind="retainer", id="r1"), "backpack", DATA)
    assert "backpack" not in npc.inventory
    assert len(npc.containers) == 1
    assert npc.containers[0].location == StorageLocation(kind="carried")
