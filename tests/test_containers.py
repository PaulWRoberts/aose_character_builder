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
