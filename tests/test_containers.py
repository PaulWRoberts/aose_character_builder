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


def _carried_backpack(fake):
    return new_container_instance("backpack", fake)


def _weapon_for_tests(item_id: str, name: str, weight_cn: int, cost_gp: int):
    from aose.models import Weapon, WeaponDamage
    return Weapon(
        id=item_id, name=name, category="weapons", item_type="weapon",
        cost_gp=cost_gp, weight_cn=weight_cn,
        damage=WeaponDamage(default="1d6", variable="1d8"),
        hands=1, melee=True, ranged=False, proficiency_group="sword",
    )


from aose.engine.shop import ContainerFull, UnknownContainer, stow


def test_stow_moves_item_from_inventory_into_container():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    inv, stashed, containers = stow(
        inventory=["torch"], stashed=[], containers=[bp],
        equipped={}, equipped_weapons=[],
        instance_id=bp.instance_id, item_id="torch", data=fake,
    )
    assert inv == []
    assert containers[0].contents == ["torch"]


def test_stow_rejects_unknown_container():
    fake = _fake_container_data()
    with pytest.raises(UnknownContainer):
        stow(["torch"], [], [], {}, [], "missing-id", "torch", fake)


def test_stow_rejects_item_not_in_inventory():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="not in inventory"):
        stow([], [], [bp], {}, [], bp.instance_id, "torch", fake)


def test_stow_rejects_equipped_item():
    fake = _fake_container_data()
    fake.items["long_sword"] = _weapon_for_tests("long_sword", "Long Sword", 60, 10)
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="equipped"):
        stow(
            inventory=["long_sword"], stashed=[], containers=[bp],
            equipped={}, equipped_weapons=["long_sword"],
            instance_id=bp.instance_id, item_id="long_sword", data=fake,
        )


def test_stow_rejects_container_item():
    fake = _fake_container_data()
    fake.items["sack"] = Container(
        id="sack", name="Sack", category="containers", item_type="container",
        cost_gp=1, weight_cn=5, capacity_cn=200,
    )
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="containers cannot be stowed"):
        stow(["sack"], [], [bp], {}, [], bp.instance_id, "sack", fake)


def test_stow_capacity_full_raises():
    fake = _fake_container_data()
    # 20 torches = 400 cn, exactly at the backpack's 400 capacity.  21st fails.
    bp = _carried_backpack(fake)
    bp = bp.model_copy(update={"contents": ["torch"] * 20})
    with pytest.raises(ContainerFull):
        stow(["torch"], [], [bp], {}, [], bp.instance_id, "torch", fake)


from aose.engine.shop import take_out


def test_take_out_from_carried_container_returns_to_inventory():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    inv, stashed, containers = take_out(
        inventory=[], stashed=[], containers=[bp],
        instance_id=bp.instance_id, item_id="torch",
    )
    assert inv == ["torch"]
    assert containers[0].contents == []


def test_take_out_from_stashed_container_returns_to_stashed_list():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed").model_copy(
        update={"contents": ["torch", "torch"]}
    )
    inv, stashed, containers = take_out(
        inventory=[], stashed=[], containers=[bp],
        instance_id=bp.instance_id, item_id="torch",
    )
    assert stashed == ["torch"]
    assert inv == []
    assert containers[0].contents == ["torch"]


def test_take_out_unknown_container_raises():
    with pytest.raises(UnknownContainer):
        take_out([], [], [], "missing-id", "torch")


def test_take_out_item_not_in_container_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="not in container"):
        take_out([], [], [bp], bp.instance_id, "torch")


from aose.engine.shop import stash_container, unstash_container


def test_stash_container_flips_state():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    result = stash_container([bp], bp.instance_id)
    assert result[0].state == "stashed"
    # Contents are untouched
    assert result[0].contents == []


def test_unstash_container_reverses():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed")
    result = unstash_container([bp], bp.instance_id)
    assert result[0].state == "carried"


def test_stash_container_unknown_raises():
    with pytest.raises(UnknownContainer):
        stash_container([], "missing-id")


def test_unstash_container_unknown_raises():
    with pytest.raises(UnknownContainer):
        unstash_container([], "missing-id")


from aose.engine.shop import ContainerNotEmpty, remove_container


def test_remove_container_drop_with_contents():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch", "torch"]})
    containers, gold = remove_container([bp], 0, bp.instance_id, "drop", fake)
    assert containers == []
    assert gold == 0  # drop refunds nothing


def test_remove_container_sell_empty_refunds_half():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    containers, gold = remove_container([bp], 0, bp.instance_id, "sell", fake)
    assert containers == []
    assert gold == 2  # 5 // 2


def test_remove_container_refund_empty_returns_full_cost():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    containers, gold = remove_container([bp], 0, bp.instance_id, "refund", fake)
    assert gold == 5


def test_remove_container_sell_non_empty_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    with pytest.raises(ContainerNotEmpty):
        remove_container([bp], 0, bp.instance_id, "sell", fake)


def test_remove_container_refund_non_empty_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    with pytest.raises(ContainerNotEmpty):
        remove_container([bp], 0, bp.instance_id, "refund", fake)


def test_remove_container_unknown_raises():
    fake = _fake_container_data()
    with pytest.raises(UnknownContainer):
        remove_container([], 0, "missing-id", "drop", fake)


def test_remove_container_bad_mode_raises():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="Unknown remove mode"):
        remove_container([bp], 0, bp.instance_id, "burn", fake)


def test_inventory_view_splits_loose_and_containers():
    fake = _fake_container_data()
    bp = _carried_backpack(fake).model_copy(update={"contents": ["torch"]})
    from aose.engine.shop import inventory_view
    view = inventory_view(
        inventory=["torch"], stashed=[], equipped={}, equipped_weapons=[],
        containers=[bp], data=fake,
    )
    # The loose torch shows up in carried; the contained torch shows up
    # under the container, not in carried.
    assert len(view.carried) == 1
    assert view.carried[0].count == 1
    assert len(view.containers) == 1
    cv = view.containers[0]
    assert cv.instance_id == bp.instance_id
    assert cv.name == "Backpack"
    assert cv.state == "carried"
    assert cv.capacity_cn == 400
    assert cv.used_cn == 20  # one torch
    assert cv.effective_weight_cn == 100  # 80 own + 1.0 * 20
    assert len(cv.contents) == 1


def test_inventory_view_container_weight_with_multiplier():
    fake = _fake_container_data()
    fake.items["boh"] = Container(
        id="boh", name="Bag of Holding", category="miscellaneous_magic_items",
        item_type="container", cost_gp=0, weight_cn=0, capacity_cn=10000,
        weight_multiplier=0.06,
    )
    bag = new_container_instance("boh", fake).model_copy(
        update={"contents": ["torch"] * 100}  # 100 * 20 = 2000 cn raw
    )
    from aose.engine.shop import inventory_view
    view = inventory_view([], [], {}, [], [bag], fake)
    cv = view.containers[0]
    assert cv.used_cn == 2000
    assert cv.effective_weight_cn == int(0.06 * 2000)  # 120


def test_inventory_view_stashed_container_zero_effective_weight():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed").model_copy(
        update={"contents": ["torch"]}
    )
    from aose.engine.shop import inventory_view
    view = inventory_view([], [], {}, [], [bp], fake)
    cv = view.containers[0]
    assert cv.state == "stashed"
    # effective_weight is only meaningful when carried; stashed = 0
    assert cv.effective_weight_cn == 0
