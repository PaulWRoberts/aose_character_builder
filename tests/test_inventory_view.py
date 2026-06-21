from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.shop import inventory_view

DATA = GameData.load(Path(__file__).parent.parent / "data")


@pytest.fixture(scope="module")
def data():
    return DATA


def test_inventory_row_carries_item_description():
    # Pick any catalog item that has a description.
    item = next(i for i in DATA.items.values() if getattr(i, "description", ""))
    view = inventory_view([item.id], [], {}, [], DATA)
    assert view.carried[0].description == item.description


def test_inventory_row_description_defaults_empty_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], DATA)
    assert view.carried[0].description == ""


from aose.engine.detail import DetailCard  # noqa: E402
from aose.models import Weapon  # noqa: E402


def test_inventory_row_carries_detail_card():
    weapon = next(i for i in DATA.items.values() if isinstance(i, Weapon))
    view = inventory_view([weapon.id], [], {}, [], DATA)
    row = view.carried[0]
    assert isinstance(row.detail, DetailCard)
    assert any(s.label == "Damage" for s in row.detail.stats)


def _base_spec(**extra):
    from aose.models import CharacterSpec, ClassEntry
    base = dict(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(extra)
    return CharacterSpec(**base)


def test_animal_group_renders_barding_in_equipped():
    from aose.models import AnimalInstance
    from aose.sheet.view import build_inventory_groups
    spec = _base_spec(animals=[AnimalInstance(
        instance_id="a1", catalog_id="war_dog", armor_id="dog_armour")])
    groups = build_inventory_groups(spec, DATA)
    animal = next(g for g in groups if g.kind == "animal")
    assert animal.has_equipped
    assert any(r.id == "dog_armour" for r in animal.equipped)


def test_retainer_group_renders_equipped_gear():
    from aose.models import CharacterSpec, ClassEntry, Retainer
    from aose.sheet.view import build_inventory_groups
    npc = CharacterSpec(
        name="Hireling",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral",
        inventory=["dagger"], equipped={"main_hand": "dagger"},
    )
    spec = _base_spec(retainers=[Retainer(id="r1", spec=npc, loyalty=7)])
    groups = build_inventory_groups(spec, DATA)
    retainer = next(g for g in groups if g.kind == "retainer")
    assert retainer.has_equipped
    assert any(r.id == "dagger" for r in retainer.equipped)


def test_inventory_row_detail_none_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], DATA)
    assert view.carried[0].detail is None


def test_off_hand_flags_for_eligible_dual_wielder():
    view = inventory_view(
        ["sword", "dagger"], [], {"main_hand": "sword"}, None, DATA,
        two_weapon=True, eligible=True, gargantua_1h_2h=False,
    )
    dagger = next(r for r in view.carried if r.id == "dagger")
    assert dagger.can_off_hand is True
    assert dagger.off_hand_blocked is False


def test_off_hand_blocked_when_off_hand_occupied():
    view = inventory_view(
        ["sword", "dagger", "shield"], [],
        {"main_hand": "sword", "off_hand": "shield"}, None, DATA,
        two_weapon=True, eligible=True, gargantua_1h_2h=False,
    )
    dagger = next(r for r in view.carried if r.id == "dagger")
    assert dagger.can_off_hand is True
    assert dagger.off_hand_blocked is True


def test_off_hand_flags_off_when_rule_disabled():
    view = inventory_view(
        ["sword", "dagger"], [], {"main_hand": "sword"}, None, DATA,
        two_weapon=False, eligible=True, gargantua_1h_2h=False,
    )
    dagger = next(r for r in view.carried if r.id == "dagger")
    assert dagger.can_off_hand is False


def test_top_level_groups_include_carried_and_carriers(data):
    from aose.models import AnimalInstance, CharacterSpec, CoinStack
    from aose.sheet.view import build_sheet
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10,
                             "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
        inventory=["torch"], coins=[CoinStack(denom="gp", count=5)],
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
    ))
    sheet = build_sheet(spec, data)
    kinds = {g.kind for g in sheet.inventory_groups}
    assert "carried" in kinds and "stashed" in kinds and "animal" in kinds
    carried = next(g for g in sheet.inventory_groups if g.kind == "carried")
    assert any(r.id == "torch" for r in carried.loose)
    assert any(c.denom == "gp" and c.count == 5 for c in carried.coins)


def test_wealth_total_on_sheet(data):
    from aose.models import CharacterSpec, CoinStack
    from aose.sheet.view import build_sheet
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10, "INT": 10,
                             "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
        coins=[CoinStack(denom="gp", count=42)],
    ))
    assert build_sheet(spec, data).total_wealth_gp == 42


def test_carried_equipped_attacks_mirror_pc_attacks(data):
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_inventory_groups
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["sword"], equipped={"main_hand": "sword"},
    )
    carried = next(g for g in build_inventory_groups(spec, data) if g.kind == "carried")
    assert carried.equipped_attacks, "PC carried group should expose weapon attack rows"
    assert any(a.name.lower().startswith("sword") for a in carried.equipped_attacks)


def test_retainer_equipped_attacks_computed_from_npc_spec(data):
    from aose.models import CharacterSpec, ClassEntry, Retainer
    from aose.sheet.view import build_inventory_groups
    npc = CharacterSpec(
        name="Hireling",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral",
        inventory=["dagger"], equipped={"main_hand": "dagger"},
    )
    spec = _base_spec(retainers=[Retainer(id="r1", spec=npc, loyalty=7)])
    retainer = next(g for g in build_inventory_groups(spec, data) if g.kind == "retainer")
    assert retainer.equipped_attacks, "retainer should expose computed attack rows"
    a = retainer.equipped_attacks[0]
    assert hasattr(a, "to_hit_ascending") and hasattr(a, "damage")


def test_animal_barding_in_equipped_worn(data):
    from aose.models import AnimalInstance
    from aose.sheet.view import build_inventory_groups
    spec = _base_spec(animals=[AnimalInstance(
        instance_id="a1", catalog_id="war_dog", armor_id="dog_armour")])
    animal = next(g for g in build_inventory_groups(spec, data) if g.kind == "animal")
    assert animal.equipped_worn, "animal barding should appear as a worn row"
    assert any(getattr(r, "item_id", None) == "dog_armour" for r in animal.equipped_worn)
