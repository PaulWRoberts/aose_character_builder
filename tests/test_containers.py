"""Tests for container items: catalog model, runtime instances, shop helpers,
weight calculations, HTTP routes."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Container

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_container_model_parses():
    c = Container(
        id="test_bag",
        name="Test Bag",
        category="containers",
        item_type="container",
        cost_gp=1,
        weight_cn=5,
        capacity_cn=200,
        weight_multiplier=1.0,
    )
    assert c.capacity_cn == 200
    assert c.weight_multiplier == 1.0


def test_container_defaults_unlimited_and_full_weight():
    c = Container(
        id="bag",
        name="Bag",
        category="containers",
        item_type="container",
        cost_gp=0,
        weight_cn=0,
    )
    assert c.capacity_cn is None
    assert c.weight_multiplier == 1.0


from aose.models import CharacterSpec, ClassEntry, ContainerInstance, RuleSet


def test_container_exceptions_exist():
    from aose.engine.shop import ContainerFull, ContainerNotEmpty, UnknownContainer
    assert issubclass(ContainerFull, ValueError)
    assert issubclass(ContainerNotEmpty, ValueError)
    assert issubclass(UnknownContainer, ValueError)


def _minimal_spec(**overrides):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
    )
    base.update(overrides)
    return CharacterSpec(**base)


def test_container_instance_construct():
    inst = ContainerInstance(
        instance_id="abc123",
        catalog_id="backpack",
        state="carried",
        contents=["torch", "rope"],
    )
    assert inst.state == "carried"
    assert inst.contents == ["torch", "rope"]


def test_character_spec_defaults_containers_empty():
    spec = _minimal_spec()
    assert spec.containers == []


from aose.engine.shop import (
    InsufficientGold,
    UnknownItem,
    add_free_container,
    buy_container,
    new_container_instance,
)
from aose.models import Container


def _fake_container_data():
    """Build a tiny GameData stand-in with one container catalog item and
    one regular item.  Lets the helper tests stay self-contained — real YAML
    loading is exercised later (Task 12)."""
    from aose.data.loader import GameData
    from aose.models import AdventuringGear

    return GameData(items={
        "backpack": Container(
            id="backpack", name="Backpack", category="containers",
            item_type="container", cost_gp=5, weight_cn=80,
            capacity_cn=400, weight_multiplier=1.0,
        ),
        "torch": AdventuringGear(
            id="torch", name="Torch", category="adventuring_gear",
            item_type="gear", cost_gp=1, weight_cn=20,
        ),
    })


def test_new_container_instance_validates_catalog_type():
    fake = _fake_container_data()
    inst = new_container_instance("backpack", fake)
    assert inst.catalog_id == "backpack"
    assert inst.state == "carried"
    assert inst.contents == []
    assert len(inst.instance_id) >= 16  # uuid4 hex length


def test_new_container_instance_rejects_non_container():
    fake = _fake_container_data()
    with pytest.raises(ValueError, match="not a container"):
        new_container_instance("torch", fake)


def test_new_container_instance_rejects_unknown_id():
    fake = _fake_container_data()
    with pytest.raises(UnknownItem):
        new_container_instance("imaginary", fake)


def test_new_container_instance_unique_ids():
    fake = _fake_container_data()
    a = new_container_instance("backpack", fake)
    b = new_container_instance("backpack", fake)
    assert a.instance_id != b.instance_id


def test_buy_container_deducts_gold_and_appends():
    fake = _fake_container_data()
    new_containers, new_gold = buy_container([], 10, "backpack", fake)
    assert len(new_containers) == 1
    assert new_containers[0].catalog_id == "backpack"
    assert new_gold == 5  # 10 - 5


def test_buy_container_rejects_insufficient_gold():
    fake = _fake_container_data()
    with pytest.raises(InsufficientGold):
        buy_container([], 2, "backpack", fake)


def test_add_free_container_does_not_deduct_gold():
    fake = _fake_container_data()
    new_containers = add_free_container([], "backpack", fake)
    assert len(new_containers) == 1
