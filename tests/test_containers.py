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


def _gp(spec):
    return next((s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried"), 0)


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
    assert inst.location.kind == "carried"
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
    one regular item.  Lets the helper tests stay self-contained â€” real YAML
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
    assert inst.location.kind == "carried"
    assert inst.contents == []
    assert len(inst.instance_id) >= 16  # uuid4 hex length


def test_new_container_instance_accepts_full_location():
    from aose.models.storage import StorageLocation
    fake = _fake_container_data()
    loc = StorageLocation(kind="animal", id="abc123")
    inst = new_container_instance("backpack", fake, location=loc)
    assert inst.location == loc
    assert inst.catalog_id == "backpack"


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
        qualities=["melee"],
    )


from aose.engine.shop import ContainerFull, UnknownContainer, stow


def test_stow_moves_item_from_inventory_into_container():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    inv, stashed, containers = stow(
        inventory=["torch"], stashed=[], containers=[bp],
        equipped={},
        instance_id=bp.instance_id, item_id="torch", data=fake,
    )
    assert inv == []
    assert containers[0].contents == ["torch"]


def test_stow_rejects_unknown_container():
    fake = _fake_container_data()
    with pytest.raises(UnknownContainer):
        stow(["torch"], [], [], {}, "missing-id", "torch", fake)


def test_stow_rejects_item_not_in_inventory():
    fake = _fake_container_data()
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="not in inventory"):
        stow([], [], [bp], {}, bp.instance_id, "torch", fake)


def test_stow_rejects_equipped_item():
    fake = _fake_container_data()
    fake.items["sword"] = _weapon_for_tests("sword", "Long Sword", 60, 10)
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="equipped"):
        stow(
            inventory=["sword"], stashed=[], containers=[bp],
            equipped={"main_hand": "sword"},
            instance_id=bp.instance_id, item_id="sword", data=fake,
        )


def test_stow_rejects_container_item():
    fake = _fake_container_data()
    fake.items["sack"] = Container(
        id="sack", name="Sack", category="containers", item_type="container",
        cost_gp=1, weight_cn=5, capacity_cn=200,
    )
    bp = _carried_backpack(fake)
    with pytest.raises(ValueError, match="containers cannot be stowed"):
        stow(["sack"], [], [bp], {}, bp.instance_id, "sack", fake)


def test_stow_capacity_full_raises():
    fake = _fake_container_data()
    # 20 torches = 400 cn, exactly at the backpack's 400 capacity.  21st fails.
    bp = _carried_backpack(fake)
    bp = bp.model_copy(update={"contents": ["torch"] * 20})
    with pytest.raises(ContainerFull):
        stow(["torch"], [], [bp], {}, bp.instance_id, "torch", fake)


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
    assert result[0].location.kind == "stashed"
    # Contents are untouched
    assert result[0].contents == []


def test_unstash_container_reverses():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed")
    result = unstash_container([bp], bp.instance_id)
    assert result[0].location.kind == "carried"


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
        inventory=["torch"], stashed=[], equipped={},
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
    view = inventory_view([], [], {}, [bag], fake)
    cv = view.containers[0]
    assert cv.used_cn == 2000
    assert cv.effective_weight_cn == int(0.06 * 2000)  # 120


def test_inventory_view_stashed_container_zero_effective_weight():
    fake = _fake_container_data()
    bp = new_container_instance("backpack", fake, state="stashed").model_copy(
        update={"contents": ["torch"]}
    )
    from aose.engine.shop import inventory_view
    view = inventory_view([], [], {}, [bp], fake)
    cv = view.containers[0]
    assert cv.state == "stashed"
    # effective_weight is only meaningful when carried; stashed = 0
    assert cv.effective_weight_cn == 0


# â”€â”€ carried_weight_cn includes containers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_carried_weight_includes_carried_container_own_weight(data):
    """A carried Backpack (80 cn) contributes 80 even when empty."""
    import copy
    from aose.engine.encumbrance import carried_weight_cn
    test_data = copy.deepcopy(data)
    test_data.items["backpack"] = Container(
        id="backpack", name="Backpack", category="containers",
        item_type="container", cost_gp=5, weight_cn=80, capacity_cn=400,
        weight_multiplier=1.0,
    )
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="carried", contents=[],
    )]
    assert carried_weight_cn(spec, test_data) == 80


def test_carried_weight_includes_contents_via_multiplier(data):
    """A carried Backpack with two daggers inside.
    80 (bag) + 1.0 * 20 (contents: 2 × 10 cn) = 100 cn."""
    import copy
    from aose.engine.encumbrance import carried_weight_cn
    test_data = copy.deepcopy(data)
    test_data.items["backpack"] = Container(
        id="backpack", name="Backpack", category="containers",
        item_type="container", cost_gp=5, weight_cn=80, capacity_cn=400,
        weight_multiplier=1.0,
    )
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="carried",
        contents=["dagger", "dagger"],
    )]
    assert carried_weight_cn(spec, test_data) == 80 + 20


def test_stashed_container_contributes_zero(data):
    import copy
    from aose.engine.encumbrance import carried_weight_cn
    test_data = copy.deepcopy(data)
    test_data.items["backpack"] = Container(
        id="backpack", name="Backpack", category="containers",
        item_type="container", cost_gp=5, weight_cn=80, capacity_cn=400,
    )
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="backpack", state="stashed",
        contents=["torch", "torch"],
    )]
    assert carried_weight_cn(spec, test_data) == 0


def test_bag_of_holding_at_full_weighs_600(data):
    """Bag of Holding at 10 000 cn raw: 0 own + int(0.06 * 10000) = 600.
    Uses 1000 daggers (10 cn each) to produce 10 000 cn of contents."""
    import copy
    from aose.engine.encumbrance import carried_weight_cn
    test_data = copy.deepcopy(data)
    test_data.items["boh"] = Container(
        id="boh", name="Bag of Holding", category="miscellaneous_magic_items",
        item_type="container", cost_gp=0, weight_cn=0, capacity_cn=10000,
        weight_multiplier=0.06,
    )
    spec = _minimal_spec(ruleset=RuleSet(encumbrance="detailed"))
    spec.containers = [ContainerInstance(
        instance_id="x", catalog_id="boh", state="carried",
        contents=["dagger"] * 1000,
    )]
    assert carried_weight_cn(spec, test_data) == int(0.06 * 10000)


def test_equip_rejects_container_catalog_item():
    from aose.engine.equip import equip
    fake = _fake_container_data()
    with pytest.raises(ValueError, match="not equippable"):
        equip("backpack", inventory=["backpack"], equipped={}, enchanted=[], data=fake)


def test_containers_yaml_loads(data):
    assert "backpack" in data.items
    bp = data.items["backpack"]
    assert isinstance(bp, Container)
    assert bp.capacity_cn == 400


def test_bag_of_holding_loaded(data):
    assert "bag_of_holding" in data.items
    boh = data.items["bag_of_holding"]
    assert isinstance(boh, Container)
    assert boh.capacity_cn == 10000
    assert boh.weight_multiplier == 0.06
    assert boh.category == "miscellaneous_magic_items"


def test_shop_categories_includes_adventuring_gear_and_magic(data):
    from aose.engine.shop import shop_categories
    cats = {c.id for c in shop_categories(data)}
    assert "adventuring_gear" in cats       # containers now live here
    assert "miscellaneous_magic_items" in cats


# â”€â”€ HTTP routes: /buy and /add for container catalog items â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.web.app import create_app


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir,
        drafts_dir=drafts_dir, examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    client._drafts_dir = drafts_dir
    return client


def _seed_character(client, gold=100, inventory=None, containers=None) -> str:
    spec = _minimal_spec(
        gold=gold,
        inventory=list(inventory or []),
        containers=list(containers or []),
    )
    save_character("test", spec, client._characters_dir)
    return "test"


def test_sheet_buy_creates_container_instance(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/buy", data={"item_id": "backpack"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert _gp(spec) == 15  # 20 - 5
    # Container is in spec.containers, NOT in inventory
    assert spec.inventory == []
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "backpack"
    assert spec.containers[0].location.kind == "carried"


def test_sheet_add_creates_container_instance_without_gold_deduction(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert _gp(spec) == 20  # unchanged
    assert len(spec.containers) == 1
    assert spec.containers[0].catalog_id == "bag_of_holding"


def test_sheet_buy_regular_item_still_uses_inventory(tmp_path):
    """Non-container Buy is unchanged."""
    client = _make_client(tmp_path)
    _seed_character(client, gold=20)
    r = client.post("/character/test/equipment/buy", data={"item_id": "sword"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["sword"]
    assert spec.containers == []


# â”€â”€ Wizard /buy and /add for container catalog items â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from aose.characters import load_draft, save_draft


def _walk_to_equipment(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on",
        "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on",
    })
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Tester", "alignment": "law"})
    client.get(f"/wizard/{draft_id}/equipment")
    return draft_id


def test_wizard_buy_creates_container_in_draft(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 100
    save_draft(draft_id, draft, client._drafts_dir)
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "backpack"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft["containers"][0]["catalog_id"] == "backpack"
    assert draft["gold"] == 95


def test_wizard_add_creates_container_without_spending_gold(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    before_gold = load_draft(draft_id, client._drafts_dir)["gold"]
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft["gold"] == before_gold  # Add is free


def test_sheet_stow_endpoint(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0, inventory=["torch"])
    # Add a backpack via add route (avoids importing the engine helpers)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == []
    assert spec.containers[0].contents == ["torch"]


def test_sheet_take_out_endpoint(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/take-out", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["torch"]
    assert spec.containers[0].contents == []


def test_sheet_stow_rejects_full_container(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "sack_small"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    # 20 daggers at 10 cn = 200 cn = sack_small capacity
    for _ in range(20):
        client.post("/character/test/equipment/add", data={"item_id": "dagger"})
        client.post("/character/test/equipment/stow", data={
            "instance_id": instance_id, "item_id": "dagger",
        })
    client.post("/character/test/equipment/add", data={"item_id": "dagger"})
    r = client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "dagger",
    })
    assert r.status_code == 400
    assert "full" in r.text.lower()


def test_wizard_stow_endpoint(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "backpack"})
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    r = client.post(f"/wizard/{draft_id}/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"] == []
    assert draft["containers"][0]["contents"] == ["torch"]


def test_wizard_take_out_endpoint(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "backpack"})
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    client.post(f"/wizard/{draft_id}/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post(f"/wizard/{draft_id}/equipment/take-out", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"] == ["torch"]
    assert draft["containers"][0]["contents"] == []


def test_sheet_stash_container_flips_state(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/stash-container", data={
        "instance_id": instance_id,
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers[0].location.kind == "stashed"


def test_sheet_unstash_container_flips_state(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/stash-container", data={
        "instance_id": instance_id,
    })
    r = client.post("/character/test/equipment/unstash-container", data={
        "instance_id": instance_id,
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers[0].location.kind == "carried"


def test_sheet_remove_container_drop_clears_contents(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "drop",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers == []
    assert spec.inventory == []
    assert _gp(spec) == 0


def test_sheet_remove_container_sell_non_empty_returns_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "sell",
    })
    assert r.status_code == 400


def test_sheet_remove_container_sell_empty_refunds_half(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, gold=0)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.post("/character/test/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "sell",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.containers == []
    assert _gp(spec) == 2  # 5 // 2


# â”€â”€ Wizard container routes: stash-container, remove-container â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_wizard_stash_container_endpoint(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "backpack"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    r = client.post(f"/wizard/{draft_id}/equipment/stash-container", data={
        "instance_id": instance_id,
    })
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["containers"][0]["location"]["kind"] == "stashed"


def test_wizard_remove_container_drop_clears_contents(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "backpack"})
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    client.post(f"/wizard/{draft_id}/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.post(f"/wizard/{draft_id}/equipment/remove-container", data={
        "instance_id": instance_id, "mode": "drop",
    })
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["containers"] == []
    assert draft["inventory"] == []


def test_wizard_single_move_route_moves_item(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "backpack"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    r = client.post(f"/wizard/{draft_id}/inventory/move", data={
        "category": "item", "item_id": "torch",
        "src_kind": "carried", "src_id": "",
        "dest_kind": "container", "dest_id": instance_id,
    })
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert "torch" not in draft["inventory"]
    assert "torch" in draft["containers"][0]["contents"]


def test_wizard_old_move_item_route_is_gone(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    r = client.post(f"/wizard/{draft_id}/equipment/move-item", data={
        "item_id": "torch", "src_kind": "carried", "dest_kind": "stashed"})
    assert r.status_code == 404


def test_sheet_renders_container_row_with_capacity_badge(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    r = client.get("/character/test")
    assert r.status_code == 200
    assert f'id="modal-container-{instance_id}"' in r.text
    assert "Backpack" in r.text
    assert "0 / 400" in r.text  # capacity badge in container modal
    # Move control appears on loose carried items (covers stow-to-container as a destination)
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    r = client.get("/character/test")
    assert 'action="/character/test/inventory/move"' in r.text


def test_sheet_renders_container_contents_after_stow(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.get("/character/test")
    assert 'action="/character/test/equipment/take-out"' in r.text


def test_wizard_containers_persist_through_finalize(tmp_path):
    """The core regression: containers added in the wizard must survive
    finalization into the saved CharacterSpec."""
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    # Spend enough gold to buy a backpack
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 100
    save_draft(draft_id, draft, client._drafts_dir)

    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "backpack"})
    draft = load_draft(draft_id, client._drafts_dir)
    instance_id = draft["containers"][0]["instance_id"]
    # Add a torch and stow it inside
    client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    client.post(f"/wizard/{draft_id}/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })

    # Submit equipment step, then finalize
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)

    # The bug being regression-tested: containers were silently dropped.
    assert len(spec.containers) == 1, "containers must survive finalization"
    assert spec.containers[0].catalog_id == "backpack"
    assert spec.containers[0].contents == ["torch"]


def test_sheet_container_row_collapse_button_present(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    r = client.get("/character/test")
    assert 'data-modal="modal-container-' in r.text


def test_sheet_print_only_lists_container_contents(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    client.post("/character/test/equipment/add", data={"item_id": "backpack"})
    spec = load_character("test", client._characters_dir)
    instance_id = spec.containers[0].instance_id
    client.post("/character/test/equipment/add", data={"item_id": "torch"})
    client.post("/character/test/equipment/stow", data={
        "instance_id": instance_id, "item_id": "torch",
    })
    r = client.get("/character/test")
    # The print-only block names the container and its contents
    assert "Backpack" in r.text
    assert "Torch" in r.text


# ── Post-cleanup data shape ──────────────────────────────────────────────────

def test_table_containers_are_adventuring_gear_category(data):
    for cid, cap in (("backpack", 400), ("sack_small", 200), ("sack_large", 600)):
        item = data.items[cid]
        assert isinstance(item, Container)
        assert item.category == "adventuring_gear"
        assert item.capacity_cn == cap


def test_bag_of_holding_still_a_container(data):
    boh = data.items["bag_of_holding"]
    assert isinstance(boh, Container)
    assert boh.magic is True
    assert boh.capacity_cn == 10000


def test_dropped_and_renamed_ids_absent(data):
    # "bedroll" and "saddle_bags" are now valid items; only the other legacy stubs remain absent
    for gone in ("candle", "iron_spikes", "wine_skin"):
        assert gone not in data.items


def test_gear_bundle_counts(data):
    assert data.items["torch"].bundle_count == 6
    assert data.items["iron_spike"].bundle_count == 12
    assert data.items["iron_rations"].bundle_count == 7
    assert data.items["standard_rations"].bundle_count == 7
    assert data.items["wine_pint"].bundle_count == 2
    assert data.items["crowbar"].bundle_count == 1


def test_containers_yaml_deleted():
    from pathlib import Path
    assert not (Path("data") / "equipment" / "containers.yaml").exists()
