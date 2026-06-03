"""Phase-2 bulk magic-item import: load-and-spot-check against real data."""
import random
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Armor, MagicItem, Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_gear_preserves_referenced_ids(data):
    for gid in ("torch", "crowbar", "lantern", "waterskin", "thieves_tools"):
        assert gid in data.items
    assert data.items["torch"].weight_cn == 20


def test_gear_has_descriptions(data):
    assert data.items["crowbar"].description
    assert "forcing doors" in data.items["crowbar"].description.lower()


def test_gear_adds_new_markdown_items(data):
    for gid in ("garlic", "grappling_hook", "holy_symbol", "wolfsbane", "pole_10ft"):
        assert gid in data.items


def test_containers_have_descriptions(data):
    bp = data.items["backpack"]
    assert "400 coins" in (bp.description or "")
    assert data.items["bag_of_holding"].magic is True


def test_armour_shield_enchantments(data):
    e = data.enchantments
    assert e["armour_plus_3"].kind == "armor" and e["armour_plus_3"].magic_bonus == 3
    assert e["shield_plus_2"].kind == "shield" and e["shield_plus_2"].magic_bonus == 2
    assert e["cursed_armour_minus_1"].magic_bonus == -1
    assert e["cursed_armour_minus_1"].cursed is True
    ac9 = e["cursed_armour_ac_9"]
    assert ac9.cursed is True
    assert ac9.modifiers[0].target == "ac" and ac9.modifiers[0].op == "set"
    assert ac9.modifiers[0].value == 9


def test_sword_enchantments(data):
    e = data.enchantments
    assert e["short_sword_of_quickness"].magic_bonus == 2
    assert e["short_sword_of_quickness"].applies_to.include == ["short_sword"]
    vsdrag = e["sword_plus_1_vs_dragons"]
    assert vsdrag.magic_bonus == 1 and vsdrag.conditional_bonus.bonus == 2
    assert e["sword_minus_1_berserker"].cursed is True
    assert e["sword_minus_1_berserker"].magic_bonus == -1
    assert e["sword_energy_drain"].charge_dice == "1d4+4"
    assert e["sword_nine_lives_stealer"].max_charges == 9
    assert e["sword_holy_avenger"].modifiers[0].target == "save:spells"
    assert e["sword_holy_avenger"].modifiers[0].value == 4
    assert e["sword_defender"].magic_bonus == 3 and e["sword_defender"].modifiers == []
    assert e["luck_blade"].charge_dice == "1d4"
    assert e["luck_blade"].modifiers[0].target == "save:all"


def test_rolled_modifier_rolls_into_extra_modifiers():
    """A MagicItem.rolled_modifiers entry becomes a concrete per-instance
    extra_modifier with a rolled value when the instance is created."""
    from aose.engine.magic import new_magic_instance
    d = GameData()
    d.items["test_bracers"] = MagicItem(
        id="test_bracers", name="Test Bracers", category="x", item_type="magic",
        cost_gp=0, magic=True, equippable=True,
        rolled_modifiers=[{"target": "ac", "op": "set", "dice": "1d4+3"}],
    )
    inst = new_magic_instance("test_bracers", d, rng=random.Random(1))
    assert len(inst.extra_modifiers) == 1
    m = inst.extra_modifiers[0]
    assert m.target == "ac" and m.op == "set" and 4 <= m.value <= 7
